#!/usr/bin/env python3

"""
 " ScummVM - Graphic Adventure Engine
 "
 " ScummVM is the legal property of its developers, whose names
 " are too numerous to list here. Please refer to the COPYRIGHT
 " file distributed with this source distribution.
 "
 " This program is free software; you can redistribute it and/or
 " modify it under the terms of the GNU General Public License
 " as published by the Free Software Foundation; either version 2
 " of the License, or (at your option) any later version.
 "
 " This program is distributed in the hope that it will be useful,
 " but WITHOUT ANY WARRANTY; without even the implied warranty of
 " MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 " GNU General Public License for more details.
 "
 " You should have received a copy of the GNU General Public License
 " along with this program; if not, write to the Free Software
 " Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 "
"""

import argparse
import csv
import io
import os
import subprocess
import sys
import urllib.request
import xml.dom.minidom
import xml.etree.ElementTree as ElemTree
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path
from typing import Tuple, final, Set, AnyStr, List
from zipfile import ZipFile

MIN_PYTHON: final = (3, 8)

URLHEAD: final = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQamumX0p-DYQa5Umi3RxX-pHM6RZhAj1qvUP0jTmaqutN9FwzyriRSXlO9rq6kR60pGIuPvCDzZL3s/pub?output=tsv"

GUID: final = namedtuple('Guid', ['filename_root', 'gid', 'element_name'])

#               filename/root,  gid,          element name
GUIDS: final = {GUID(filename_root='games', gid='1946612063', element_name='game'),
                GUID(filename_root='engines', gid='0', element_name='engine'),
                GUID(filename_root='companies', gid='226191984', element_name='company'),
                GUID(filename_root='series', gid='1095671818', element_name='serie')
                }

URL_ICONS_LIST: final = 'https://downloads.scummvm.org/frs/icons/LIST'

ICON_DIR: final = 'icons'
ENCODING: final = 'utf-8'

ZIP_NAME_PREFIX: final = 'gui-icons-'
ZIP_NAME_EXTENSION: final = '.dat'
ZIP_DATE_FORMAT: final = '%Y%m%d'

LIST_NAME: final = 'LIST'
LIST_DELIM: final = ','

DATE_FORMAT: final = '%Y-%m-%d'

FIRST_HASH: final = 'b2a20aad85714e0fea510483007e5e96d84225ca'

ChangedFileSet = Set[str]


def main(last_update: datetime, last_hash: str, listfile_entries: List[str]) -> None:
    """Our main function.

    :param last_update: datetime
            An optional last_update datetime. Day + 1 after the last creation of icons.zip
            If not present please provide last_hash
    :param last_hash: str
            The (newest) last_hash value of the LIST file. It is preferred to use this param.
    :param listfile_entries: List[str]
            When the LIST file is already read (finding last_hash) than we could reuse it.
    """

    if last_update is None and last_hash is None:
        print('Please provider either last_update or last_hash')
        sys.exit(1)

    # ### Step 1: Generating XMLs
    xml_file_names = generate_xmls()

    # ### Step 2: Creating a zip file with the changed icons (only icons directory!)
    changed_icon_file_names = get_changed_icon_file_names(last_update, last_hash)

    # ### Step 3: pack xmls / icons into one zip
    new_iconsdat_name = write_iconsdat(list(changed_icon_file_names) + xml_file_names)

    # ### Step 4: create new LIST file
    new_listfile_name = write_new_listfile(new_iconsdat_name, listfile_entries)

    print('\nPls upload/commit the new files:')
    print('\t' + new_iconsdat_name)
    print('\t' + new_listfile_name)


def generate_xmls() -> List[str]:
    """Generates the XMLs to be stored in the new zip file.

    :return: a List of generated XML files.
    """
    print('Step 1: generate XMLs')

    xml_files = []

    for guid in GUIDS:
        url = URLHEAD + "&gid=" + guid.gid

        print("Processing " + guid.filename_root + "... ", end="", flush=True)

        root = ElemTree.Element(guid.filename_root)

        with urllib.request.urlopen(url) as file:
            output = csv.DictReader(io.StringIO(file.read().decode(ENCODING)), delimiter='\t')
            for product in output:
                product_xml = ElemTree.SubElement(root, guid.element_name)
                for key, value in product.items():
                    product_xml.set(key, value)

        dom = xml.dom.minidom.parseString(ElemTree.tostring(root).decode(ENCODING))

        #   on win machines there could be an error without specifying utf-8
        xml_file_name = guid.filename_root + ".xml"
        with open(xml_file_name, "w", encoding=ENCODING) as file:
            file.write(dom.toprettyxml())

        xml_files.append(xml_file_name)
        print("done")

    return xml_files


def get_changed_icon_file_names(last_update: datetime, last_hash: str) -> ChangedFileSet:
    """Returns all changed ICON file names.

    :param last_update: last update as datetime (hash is preferred)
    :param last_hash: the hash of the last commit (stored in last entry of the LIST file)
    :return: a ChangedFileSet with all changed icons.
    """

    if last_hash:
        print('\nStep 2: fetching changed icons using hash ' + last_hash)
        last_iconsdat_date = None
    else:
        last_iconsdat_date = last_update.strftime(DATE_FORMAT)
        print('\nStep 2: fetching changed icons since ' + last_iconsdat_date)

    check_isscummvmicons_repo()

    is_repo_uptodate()

    if last_hash:
        commit_hash = last_hash
    else:
        commit_hashes = get_commit_hashes(last_iconsdat_date)

        # no changes nothing to do
        if len(commit_hashes) < 1:
            print('no new /changed icons since: ' + last_iconsdat_date)
            sys.exit(1)

        # last (sorted reverse!) commit_hash is sufficient
        commit_hash = commit_hashes[0]

    return collect_commit_file_names(commit_hash)


def write_new_listfile(new_iconsdat_name: str, listfile_entries: List[str]) -> str:
    """Writes a new LIST file.

    :param new_iconsdat_name: the name of the new iconds-dat file.
    :param listfile_entries: the entries of the LIST file (if already read) - an empty list is Ok.
    :return: the name of the LIST file written.
    """
    print('\nStep 4: generating a new ' + LIST_NAME + ' file')

    if len(listfile_entries) < 1:
        tmp_listfile_entries = get_listfile_entries()
    else:
        print(LIST_NAME + ' already read - using given values')
        tmp_listfile_entries = listfile_entries

    last_commit_master = get_last_hash_from_master()

    new_iconsdat_size = os.path.getsize(new_iconsdat_name)
    tmp_listfile_entries.append(
        new_iconsdat_name + LIST_DELIM + str(new_iconsdat_size) + LIST_DELIM + last_commit_master)

    if os.path.exists(LIST_NAME):
        print(LIST_NAME + ' exists - file will be overwritten')

    print('writing new ' + LIST_NAME + ' entries...', end='', flush=True)

    with open(LIST_NAME, mode='w', encoding=ENCODING) as outfile:
        outfile.write('\n'.join(tmp_listfile_entries))

    print('done')
    return LIST_NAME


def get_last_hash_from_master() -> str:
    """Reads the last hash code from the origin/master.

    :return: the hash of the latest commit.
    """
    lines = run_git('rev-parse', 'HEAD')
    if len(lines) < 1:
        print('ERROR: no commit found')
        sys.exit(1)

    return lines[0].decode(ENCODING).rstrip()


def get_listfile_lasthash() -> Tuple[str, List[str]]:
    """Reads the LIST file and returns the last hash and the list of lines.

    :return: A String with the last hash (from the LIST file) and a List containing all the lines of the LIST file.
    """
    print('no inputDate argument - fetching last hash from ' + LIST_NAME + '... ', flush=True)

    listfile_entries = get_listfile_entries()

    last_entry_values = listfile_entries[-1].split(LIST_DELIM)

    if len(last_entry_values) == 1 or len(last_entry_values) == 2:
        # remove this if/else after LIST file is committed with FIRST_HASH and just use else print/quit()
        if len(listfile_entries) == 1:
            print("WARNING: Workaround - fixing first line of LIST file! Pls remove this fix after the first run")
            last_entry_values.append(FIRST_HASH)
            listfile_entries[0] = listfile_entries[0].rstrip() + "," + FIRST_HASH
    else:
        print("Wrong LIST entry format - please add inputDate argument yyyymmdd and run the script again")
        sys.exit(1)

    return last_entry_values[2], listfile_entries


def get_listfile_entries() -> List[str]:
    """Reads and returns all lines / entries of the LIST file.

    :return: a List of strings with the content of the LIST file.
    """
    print('reading existing ' + LIST_NAME + ' entries...', end='', flush=True)
    with urllib.request.urlopen(URL_ICONS_LIST) as file:
        output = file.read().decode(ENCODING).splitlines()
        print('done')
        return output


def check_isscummvmicons_repo() -> None:
    """Different checks for the local repo - will quit() the srcipt if there is any error."""
    print('checking local directory is scummvm-icons repo ... ', end='', flush=True)

    output_show_origin = run_git('remote', 'show', 'origin')

    if not is_any_git_repo(output_show_origin):
        print('error')
        print('not a git repository (or any of the parent directories)')
        sys.exit(1)

    # wrong repo
    if not is_scummvmicons_repo(output_show_origin):
        print('error')
        print('local folder is not a scummvm-icons git repo')
        sys.exit(1)

    print('done')


def is_scummvmicons_repo(output_showorigin: List[AnyStr]) -> bool:
    """ Checks if the local repo is a scummvm-icons repo"""

    # should be the correct repo
    if any('Fetch URL: https://github.com/scummvm/scummvm-icons' in line.decode(ENCODING)
           for line in output_showorigin):
        return True

    return False


def is_any_git_repo(output_showorigin: List[AnyStr]) -> bool:
    """Checks if the local folder belongs to a git repo.

    :param output_showorigin: The output of 'show origin'.
    :return: True if it is a git repo
    """

    # outside of any local git repo
    if any('fatal: not a git repository' in line.decode(ENCODING) for line in output_showorigin):
        return False

    return True


def is_repo_uptodate() -> bool:
    """Checks if the local repo is up to date.

    :return: True if the local repo is up-to-date
    """

    # ### check local repo is up to date
    print('checking local repo is up to date...', end='', flush=True)

    if len(run_git('fetch', '--dry-run')) > 0:
        print('warning')
        print('fetch with changes - make sure that your local branch is up to date')
        return False

    # second variant of check
    run_git('update-index', '--refresh', '--unmerged')
    if len(run_git('diff-index', '--quiet', 'HEAD')) > 0:
        print('warning')
        print('fetch with changes - make sure that your local branch is up to date')
        return False

    print('done')
    return True


def get_commit_hashes(last_icondat_date: str) -> List[str]:
    """Collects all commit hashes since a given date.

    :param last_icondat_date: last icon-dat generation date.
    :return: all commits since last_icondat_date.
    """

    commit_hashes = []
    # using log with reverse to fetch the commit_hashes
    for commit_lines in run_git('log', '--reverse', '--oneline', "--since='" + last_icondat_date + "'"):
        # split without sep - runs of consecutive whitespace are regarded as a single separator
        commit_hashes.append(commit_lines.decode(ENCODING).split(maxsplit=1)[0])

    return commit_hashes


def collect_commit_file_names(commit_hash: str) -> ChangedFileSet:
    """Collects all filnames (icons) from a git commit.

    :param commit_hash: the hash of the git commit.
    :return: all changed icons (from the 'icons' directory)
    """

    changed_file_set = set()  # set, no duplicates
    print('fetching file names for commit:' + commit_hash + ' ... ', end='', flush=True)

    for file in run_git('diff', '--name-only', commit_hash + '..'):

        # stdout will contain bytes - convert to utf-8 and strip cr/lf if present
        git_file_name = file.decode(ENCODING).rstrip()

        if git_file_name.startswith(ICON_DIR + '/') or git_file_name.startswith(ICON_DIR + 'icons\\'):

            # build local path with a defined local folder / sanitize filenames
            local_path = '.' + os.path.sep + ICON_DIR + os.path.sep + Path(git_file_name).name

            # file must exist / running from wrong path would result in non existing files
            if os.path.exists(local_path):
                changed_file_set.add(local_path)
            else:
                print('WARNING: file "' + local_path + '" is not in local repo - deleted? ')

    print('done')
    print(f'icons (files) changed: {len(changed_file_set)}')

    return changed_file_set


def write_iconsdat(changed_files: List[str]) -> str:
    """Creates a new file (will overwrite existing files) packing all changed_files into it.

    :param changed_files: The changes files (icons) for the new icons-dat file.
    :return: a string with the name of the created zip (icons-dat) file.
    """

    print('\nStep 3: generating a new zip file...')

    # using today for the zip name
    today = date.today()

    zip_name = ZIP_NAME_PREFIX + today.strftime(ZIP_DATE_FORMAT) + ZIP_NAME_EXTENSION
    if os.path.exists(zip_name):
        print(zip_name + ' exists - file will be overwritten')

    print('creating zip ' + zip_name + '... ', end='', flush=True)

    with ZipFile(zip_name, mode='w', compresslevel=9) as new_entries:
        for changed_file in changed_files:
            new_entries.write(changed_file)
    print('done')

    return zip_name


def run_git(*git_args) -> List[AnyStr]:
    """Executes a git command and returns the stdout (as Line[AnyStr])

    :param *git_args:  A string, or a sequence of program arguments.
    :return: The StdOut as List[AnyStr]
    """

    my_env = os.environ.copy()  # copy current environ
    my_env["LANG"] = "C"  # add lang C
    with subprocess.Popen(args=['git'] + list(git_args), stdout=subprocess.PIPE, env=my_env) as child_proc:
        return child_proc.stdout.readlines()


###########

if sys.version_info < MIN_PYTHON:
    sys.exit(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or later is required.\n")

# check args / get date
argParser = argparse.ArgumentParser(usage='%(prog)s [lastUpdate]')
argParser.add_argument('lastUpdate', help='last update - date format: yyyymmdd', default=argparse.SUPPRESS, nargs='?')
args = argParser.parse_args()

# optional param, if not present fetch last_update from the LIST file
if 'lastUpdate' in args:
    arg_last_update = datetime.strptime(args.lastUpdate, '%Y%m%d')
    print('using provided inputDate: ' + arg_last_update.strftime(DATE_FORMAT) + '\n')

    # we have to read the LIST later (if needed)
    main(arg_last_update, "", [])

else:
    arg_last_hash, arg_listfile_entries = get_listfile_lasthash()
    print('using last hash from ' + LIST_NAME + ': ' + arg_last_hash + '\n')

    # listfile_entries as param, no need the read the LIST file twice
    main(None, arg_last_hash, arg_listfile_entries)
