#!/usr/bin/env python

# WARNING: This script will use your current OMERO login session if one
# exists. If you want to use a different login ensure you logout first.

import csv
import os
import omero.clients
import omero.cli

from uploadinplace import upload_ln_s

DRYRUN = False
OMERO_DATA_DIR = '/data/OMERO'
NAMESPACE = 'openmicroscopy.org/idr/analysis/original'


def list_files(rootdir):
    # with open('idr0047-neuert-20180911-ftp.txt') as f:
    #     files = [line.strip() for line in f.readlines()]
    files = [os.path.join(fileparts[0], filename)
             for fileparts in os.walk(rootdir)
             for filename in fileparts[2]
             if fileparts[2]]

    uploads = [fn for fn in files
               if os.path.splitext(fn)[1] not in ('.tif', '.tiff')]
    assert set(os.path.splitext(fn)[1] for fn in uploads) == set(
        ['.csv', '.mat'])
    return uploads


def upload_and_attach(conn, uploads, attachmap, datasets, images,
                      failifexists=True, dryrun=False):
    for filepath in uploads:
        if filepath.endswith('csv'):
            # https://tools.ietf.org/html/rfc7111
            mimetype = 'text/csv'
        else:
            # http://justsolve.archiveteam.org/wiki/MAT
            mimetype = 'application/x-matlab-data'

        try:
            targetname = attachmap[filepath]
        except KeyError:
            print('ERROR: Unmentioned file found, ignoring: %s' % filepath)
            continue
        try:
            target = images[targetname]
        except KeyError:
            target = datasets[targetname]

        existingfas = set(
            a.getFile().name for a in target.listAnnotations()
            if isinstance(a, omero.gateway.FileAnnotationWrapper))
        filename = os.path.split(filepath)[1]
        if filename in existingfas:
            msg = 'File %s already attached to %s' % (filename, target)
            if failifexists:
                raise Exception(msg)
            else:
                print('WARNING: %s, skipping' % msg)
                continue

        print('Attaching %s to %s (%s %s %s)' % (
              filename, target, filepath, mimetype, NAMESPACE))
        if not dryrun:
            fo = upload_ln_s(filepath, conn, OMERO_DATA_DIR, mimetype)
            fa = omero.model.FileAnnotationI()
            fa.setFile(fo._obj)
            fa.setNs(omero.rtypes.rstring(NAMESPACE))
            fa = conn.getUpdateService().saveAndReturnObject(fa)
            fa = omero.gateway.FileAnnotationWrapper(conn, fa)
            target.linkAnnotation(fa)


def parse_processed_file(filename, rootdir):
    """
    Create a mapping of processesd-file-path: dataset-or-image-name
    """
    attachmap = {}
    with open(filename) as f:
        for line in csv.reader(f, delimiter='\t'):
            parent, relpath, description = line
            if parent.startswith('#') or parent in ('Experiment', ''):
                continue
            filepath = os.path.join(rootdir, relpath)
            attachmap[filepath] = parent
    return attachmap


def get_omero_targets(conn, projectname):
    """
    Get all OMERO datasets and images in this project
    """
    project = conn.getObject('Project', attributes={'name': projectname})
    assert project
    datasets = {}
    images = {}
    for d in project.listChildren():
        datasets[d.name] = d
        for i in d.listChildren():
            images[i.name] = i
    return datasets, images


def main(conn):
    rootdir = '/uod/idr/filesets/idr0047-neuert-yeastmRNA/20181016-ftp'
    uploads = list_files(rootdir)
    attachmap = parse_processed_file(
        '../experimentA/idr0047-experimentA-processed.txt', rootdir)
    datasets, images = get_omero_targets(
        conn, 'idr0047-neuert-yeastmrna/experimentA')

    # Cross-check
    datasetsimages = set(datasets.keys()).union(images.keys())
    attach_without_target = set(attachmap.values()).difference(
        datasetsimages)
    uploads_without_attach = set(uploads).difference(attachmap.keys())

    assert attach_without_target == set(), '\n  '.join(
        [''] + sorted(attach_without_target))
# There are some extra files that aren't in idr0047-experimentA-processed.txt
# Ignore them instead of aborting
#    assert uploads_without_attach == set(), '\n  '.join(
#        [''] + sorted(uploads_without_attach))
    if uploads_without_attach:
        print('\n  '.join(
              ['WARNING: Unexpected files, these will not be uploaded:'] +
              sorted(uploads_without_attach)))

    upload_and_attach(conn, uploads, attachmap, datasets, images,
                      failifexists=True, dryrun=DRYRUN)


if __name__ == '__main__':
    with omero.cli.cli_login() as c:
        conn = omero.gateway.BlitzGateway(client_obj=c.get_client())
        main(conn)
