#!/usr/bin/env python

import argparse
import os
import os.path
import stat
import shutil
import zipfile
import glob
import fnmatch
import json

from .context import temp_directory
from .pip_automation import save_wheels
from .executable import make_executable

this_file = os.path.realpath(__file__)
this_directory = os.path.dirname(this_file)
build_skel = os.path.join(this_directory, 'build_skel')


def stage_bundle(cli_args):
    archive_basename = "%s_%s" % (cli_args.name, cli_args.label)
    executable_path = os.path.join(os.getcwd(), archive_basename + '.zip')

    if os.path.exists(executable_path) and not cli_args.f:
        print "%s already exists, skipping. Call with -f to force rebuild" % executable_path
        return

    with temp_directory() as staging_dir:
        build_dir = os.path.join(staging_dir, cli_args.label)

        shutil.copytree(build_skel, build_dir)

        # these are wheels needed during activation
        bootstrap_wheels = ['virtualenv', 'pip', 'wheel', 'setuptools']
        bootstrap_wheels_destination = os.path.join(
            build_dir, 'bootstrap_wheels')
        save_wheels(packages=bootstrap_wheels,
                    destination=bootstrap_wheels_destination)

        # move just the wheels we want into the bundle dir
        wheel_destination = os.path.join(build_dir, 'wheels')
        if cli_args.r:
            save_wheels(
                destination=wheel_destination,
                requirements_paths=cli_args.r)

        # copy django project into bundle dir
        project_complete_path = os.path.join(
            os.getcwd(), cli_args.project_path)
        project_norm_path = os.path.normpath(project_complete_path)
        project_slug = os.path.basename(project_norm_path)
        project_destination = os.path.join(build_dir, project_slug)
        shutil.copytree(cli_args.project_path, project_destination)

        # install paths.d/0_build.json, so activate.sh can find the django_root
        paths_d = os.path.join(build_dir, 'paths.d')
        initial_paths_path = os.path.join(paths_d, '0_build.json')

        with open(initial_paths_path, 'wb') as initial_paths_file:
            json.dump({'django_root': project_slug}, initial_paths_file)

        if cli_args.static:
            for index, path in enumerate(cli_args.static):
                destination = os.path.join(build_dir, 'static.in/%s/' % index)
                shutil.copytree(path, destination)

        if cli_args.aux:
            aux_root = os.path.join(build_dir, 'aux')
            for aux_spec in cli_args.aux:
                if '=' in aux_spec:
                    slug, src = aux_spec.split('=')
                else:
                    # normalize the path, so that it  will not end in a /
                    # required for basename to get the last path component
                    # would auth_path.split('/')[-1] be simpler? maybe.
                    norm_path = os.path.normpath(aux_spec)
                    slug = os.path.basename(norm_path)
                    src = aux_spec

                destination = os.path.join(aux_root, slug)
                shutil.copytree(src, destination)

        archive_name = shutil.make_archive(archive_basename,
                                           'zip',
                                           root_dir=staging_dir,
                                           base_dir=cli_args.label)

        make_executable(archive_name, prefix=cli_args.label)
        print("generated build at %s" % executable_path)


def inject_configuration(cli_args):
    with temp_directory() as staging_dir:
        build_zip_path = os.path.join(staging_dir, 'build.zip')

        shutil.copyfile(cli_args.build_zip, build_zip_path)

        build_zip = zipfile.ZipFile(build_zip_path, mode="a")

        # figuring out where things are in this zip file...
        all_the_wheels = fnmatch.filter(build_zip.namelist(), '*/wheels/*.whl')
        zip_wheel_dir = os.path.dirname(all_the_wheels[0])
        zip_root = os.path.normpath(os.path.join(zip_wheel_dir, '../'))

        # move just the wheels we want into the bundle dir
        wheel_destination = os.path.join(staging_dir, 'wheels')
        if cli_args.requirements_file:
            save_wheels(requirements_file=cli_args.requirements_file,
                        destination=wheel_destination)
            wheel_pattern = os.path.join(staging_dir, 'wheels/*.whl')

            saved_wheels = glob.glob(wheel_pattern)

            for wheel_path in saved_wheels:
                name = os.path.join(
                    zip_wheel_dir, os.path.basename(wheel_path))
                build_zip.write(wheel_path, arcname=name)

        build_zip.write(
            cli_args.vars, os.path.join(
                zip_root, 'environment.json'))

        if cli_args.paths:
            build_zip.write(
                cli_args.paths, os.path.join(
                    zip_root, 'paths.json'))

        if cli_args.prepend_wsgi:
            build_zip.write(cli_args.prepend_wsgi,
                            os.path.join(zip_root, 'pre-wsgi.py-fragment'))

        if cli_args.append_wsgi:
            build_zip.write(cli_args.append_wsgi,
                            os.path.join(zip_root, 'post-wsgi.py-fragment'))

        build_zip.close()
        build_filename = os.path.basename(cli_args.build_zip)
        name, ext = os.path.splitext(build_filename)
        release_filename = "%s_%s%s" % (name, cli_args.slug, ext)
        shutil.copyfile(build_zip_path, release_filename)


def main():
    parser = argparse.ArgumentParser(description="drama-free deployable django"
                                     " projects")

    subparsers = parser.add_subparsers()
    build_parser = subparsers.add_parser('build')
    release_parser = subparsers.add_parser('release')

    # build parser arguments
    build_parser.add_argument('project_path')

    build_parser.add_argument('name', help="name of this project")

    build_parser.add_argument('label', help="a label for this build-- "
                              "maybe a build ID or version number")

    build_parser.add_argument('-r', action='append', help="just like you would"
                              " 'pip install -r'")

    build_parser.add_argument('--aux', action='append',
                              help='extra directories to include, in form'
                              ' name=/path/to/dir.')

    build_parser.add_argument(
        '--static',
        action='append',
        help='extra directories to include in static files'
        'to be served from STATIC_ROOT')

    build_parser.add_argument(
        '-f',
        action='store_true',
        help="ignore if this build already exists")

    build_parser.set_defaults(func=stage_bundle)

    # release parser arguments
    release_parser.add_argument('build_zip', help='path to a zip file'
                                " generated with 'no-drama build'")
    release_parser.add_argument(
        'vars', help="JSON dictionary of env variables")
    release_parser.add_argument('slug', help="a label for this release")

    release_parser.add_argument('--paths', help="json file for overriding"
                                " default paths")
    release_parser.add_argument(
        '--requirements_file', help="just like you would"
        " 'pip install -r'. Let's you add more wheels to the build")

    release_parser.add_argument(
        '--prepend-wsgi',
        help="text file w/ additional python code to modify "
        "the environment before the wsgi 'application' is"
        " created")

    release_parser.add_argument(
        '--append-wsgi',
        help="text file w/ additional python code to modify "
        "the wsgi 'application'")

    release_parser.set_defaults(func=inject_configuration)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
