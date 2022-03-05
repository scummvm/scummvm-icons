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
from datetime import date
from datetime import datetime
import io
import os
from pathlib import Path
import subprocess
from typing import Tuple
import urllib.request
import xml.dom.minidom
from zipfile import ZipFile

import xml.etree.ElementTree as ET

URLHEAD = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQamumX0p-DYQa5Umi3RxX-pHM6RZhAj1qvUP0jTmaqutN9FwzyriRSXlO9rq6kR60pGIuPvCDzZL3s/pub?output=tsv"

#        filename/root  gid           element name
GUIDS = {'games'     : ('1946612063', 'game'),
         'engines'   : ('0',          'engine'),
         'companies' : ('226191984',  'company'),
         'series'    : ('1095671818', 'serie')
}

URL_ICONS_LIST = 'https://downloads.scummvm.org/frs/icons/LIST'

ICON_DIR = 'icons'
ENCODING = 'utf-8'

ZIP_NAME_PREFIX = 'gui-icons-'
ZIP_NAME_EXTENSION = '.dat'
ZIP_DATE_FORMAT = '%Y%m%d'

LIST_NAME = 'LIST'
LIST_DELIM = ','

DATE_FORMAT = '%Y-%m-%d'

FIRST_HASH = 'b2a20aad85714e0fea510483007e5e96d84225ca'


def main(last_update: datetime, last_hash: str, listfile_entries: list):
    """ Our main function

    Parameters
    ----------
    last_update : datetime
        An optional last_update datetime. Day + 1 after the last creation of icons.zip
        If not present please provide last_hash
    last_hash : str
        The (newest) last_hash value of the LIST file. It is preferred to use this param.
    listfile_entries : list
        When the LIST file is already read (finding last_hash) than we could reuse it.

    """

    if last_update is None and last_hash is None:
        print ('Please provider either last_update or last_hash')
        quit()

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


def generate_xmls():
    """ Generates the XMLs to be stored in the new zip file"""
    print('Step 1: generate XMLs')

    xml_files = []

    for guid in GUIDS:
        url = URLHEAD + "&gid=" + GUIDS[guid][0]

        print("Processing " + guid + "... ", end="", flush=True)

        root = ET.Element(guid)

        with urllib.request.urlopen(url) as f:
            output = csv.DictReader(io.StringIO(f.read().decode(ENCODING)), delimiter='\t')
            for product in output:
                product_xml = ET.SubElement(root, GUIDS[guid][1])
                for key, value in product.items():
                    product_xml.set(key, value)

        dom = xml.dom.minidom.parseString(ET.tostring(root).decode(ENCODING))

    #   on win machines there could be an error without specifying utf-8
        xml_file_name = guid + ".xml"
        with open(xml_file_name, "w", encoding=ENCODING) as f:
            f.write(dom.toprettyxml())

        xml_files.append(xml_file_name)
        print("done")

    return xml_files


def get_changed_icon_file_names(last_update: datetime, last_hash: str) -> set:
    """ Returns all changed ICON file names"""

    if last_hash:
        print('\nStep 2: fetching changed icons using hash ' + last_hash)
        last_iconsdat_date = None
    else:
        last_iconsdat_date = last_update.strftime(DATE_FORMAT)
        print('\nStep 2: fetching changed icons since ' + last_iconsdat_date)

    check_isscummvmicons_repo()

    check_isrepouptodate()

    if last_hash:
        commit_hash = last_hash
    else:
        commit_hashes = get_commithashes(last_iconsdat_date)

        # no changes nothing to do
        if len(commit_hashes) == 0:
            print('no new /changed icons since: ' + last_iconsdat_date)
            quit()

        # last (sorted reverse!) commit_hash is sufficient
        commit_hash = commit_hashes[0]

    return collect_commit_file_names(commit_hash)


def write_new_listfile(new_iconsdat_name: str, listfile_entries: list) -> str:
    """ Writes a new LIST file"""
    print('\nStep 4: generating a new ' + LIST_NAME + ' file')

    if len(listfile_entries) == 0:
        listfile_entries = get_listfile_entries()
    else:
        print(LIST_NAME + ' already read - using given values')

    last_commit_master = get_last_hash_from_master()

    new_iconsdat_size = os.path.getsize(new_iconsdat_name)
    listfile_entries.append(new_iconsdat_name + LIST_DELIM + str(new_iconsdat_size) + LIST_DELIM + last_commit_master)

    if os.path.exists(LIST_NAME):
        print(LIST_NAME + ' exists - file will be overwritten')

    print('writing new ' + LIST_NAME + ' entries...', end='', flush=True)

    with open(LIST_NAME, 'w') as outfile:
        outfile.write('\n'.join(listfile_entries))

    print('done')
    return LIST_NAME

def get_last_hash_from_master() -> str:
    lines = run_git('rev-parse', 'HEAD')
    if len(lines) < 1:
        print('ERROR: no commit found')
        quit()

    return lines[0].decode(ENCODING).rstrip()

def get_listfile_lasthash() -> Tuple[str, list]:
    """ Reads the LIST file and returns the last hash and the list of lines"""
    print('no inputDate argument - fetching last hash from ' + LIST_NAME + '... ', flush=True)

    listfile_entries = get_listfile_entries()

    values = listfile_entries[-1].split(LIST_DELIM)

    if len(values) < 3:
        # remove this if/else after LIST file is committed with FIRST_HASH and just use else print/quit()
        if len(listfile_entries) == 1:
            print("WARNING: Workaround - fixing first line of LIST file! Pls remove this fix after the first run")
            values.append(FIRST_HASH)
            listfile_entries[0] = listfile_entries[0].rstrip() + "," + FIRST_HASH
        else:
            print("Wrong/Old LIST entry format - please add inputDate argument yyyymmdd and run the script again")
            quit()

    return values[2], listfile_entries


def get_listfile_entries() -> list:
    """ Reads and returns all lines / entries of the LIST file"""
    print('reading existing ' + LIST_NAME + ' entries...', end='', flush=True)
    with urllib.request.urlopen(URL_ICONS_LIST) as f:
        output = f.read().decode(ENCODING).splitlines()
        print('done')
        return output


def check_isscummvmicons_repo():
    """ Different checks for the local repo"""
    print('checking local directory is scummvm-icons repo ... ', end='', flush=True)

    output_showorigin = run_git('remote', 'show', 'origin')

    if not is_anygitrepo(output_showorigin):
        print('error')
        print('not a git repository (or any of the parent directories)')
        quit()

    # wrong repo
    if not is_scummvmicons_repo(output_showorigin):
        print('error')
        print('local folder is not a scummvm-icons git repo')
        quit()

    print('done')


def is_scummvmicons_repo(output_showorigin: list) -> bool:
    """ Checks if the local repo is a scummvm-icons repo"""
    for line in output_showorigin:
        # should be the correct repo
        if 'Fetch URL: https://github.com/scummvm/scummvm-icons' in line.decode(ENCODING):
            return True

    return False


def is_anygitrepo(output_showorigin: list) -> bool:
    """ Checks if the local folder belongs to a git repo"""
    for line in output_showorigin:
        # outside of any local git repo
        if 'fatal: not a git repository' in line.decode(ENCODING):
            return False

    return True


def check_isrepouptodate():
    """ Checks if the local repo is up to date"""

    # ### check local repo is up to date
    print('checking local repo is up to date...', end='', flush=True)

    if len(run_git('fetch', '--dry-run')) > 0:
        print('warning')
        print('fetch with changes - make sure that your local branch is up to date')

    # second variant of check
    run_git('update-index', '--refresh', '--unmerged')
    if len(run_git('diff-index', '--quiet', 'HEAD')) > 0:
        print('warning')
        print('fetch with changes - make sure that your local branch is up to date')

    print('done')


def get_commithashes(last_icondat_date: str) -> list:
    """ Collects all commit hashes since a given date"""

    commit_hashes = []
    # using log with reverse to fetch the commit_hashes
    for cm in run_git('log', '--reverse', '--oneline', "--since='" + last_icondat_date + "'"):
        # split without sep - runs of consecutive whitespace are regarded as a single separator
        commit_hashes.append(cm.decode(ENCODING).split(maxsplit=1)[0])

    return commit_hashes


def collect_commit_file_names(commit_hash: str) -> set:
    """ Collects all filnames (icons) from a git commit"""

    changed_file_set = set()
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


def write_iconsdat(changed_files: list) -> str:
    """ Creates a new file (will overwrite existing files) packing all changed_files into it"""
    print('\nStep 3: generating a new zip file...')

    # using today for the zip name
    today = date.today()

    zip_name = ZIP_NAME_PREFIX + today.strftime(ZIP_DATE_FORMAT) + ZIP_NAME_EXTENSION
    if os.path.exists(zip_name):
        print(zip_name + ' exists - file will be overwritten')

    print('creating zip ' + zip_name + '... ', end='', flush=True)

    with ZipFile(zip_name, mode='w', compresslevel=9) as newentries:
        for cf in changed_files:
            newentries.write(cf)
    print('done')

    return zip_name


def run_git(*args):
    my_env = os.environ.copy()
    my_env["LANG"] = "C"
    """ Executes a git command and returns the stdout (as line[])"""
    with subprocess.Popen(args=['git'] + list(args), stdout=subprocess.PIPE, env=my_env) as child_proc:
        return child_proc.stdout.readlines()

###########


# check args / get date
argParser = argparse.ArgumentParser(usage='%(prog)s [lastUpdate]')
argParser.add_argument('lastUpdate', help='last update - date format: yyyymmdd', default=argparse.SUPPRESS, nargs='?')
args = argParser.parse_args()

# optional param, if not present fetch last_update from the LIST file
if 'lastUpdate' in args:
    last_update = datetime.strptime(args.lastUpdate, '%Y%m%d')
    listfile_entries = {}
    last_hash = ""
    print('using provided inputDate: ' + last_update.strftime(DATE_FORMAT) + '\n')
else:
    last_hash, listfile_entries = get_listfile_lasthash()
    last_update = None
    print('using last hash from ' + LIST_NAME + ': ' + last_hash + '\n')

# listfile_entries as param, no need the read the LIST file twice
main(last_update, last_hash, listfile_entries)
