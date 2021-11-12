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

import csv
import xml.etree.ElementTree as ET
import io
import xml.dom.minidom
import sys

import urllib.request

urlHead = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQamumX0p-DYQa5Umi3RxX-pHM6RZhAj1qvUP0jTmaqutN9FwzyriRSXlO9rq6kR60pGIuPvCDzZL3s/pub?output=tsv"

#        filename/root  gid           element name
guids = {'games'     : ('1946612063', 'game'),
         'engines'   : ('0',          'engine'),
         'companies' : ('226191984',  'company'),
         'series'    : ('1095671818', 'serie')
}

for guid in guids:
    url = urlHead + "&gid=" + guids[guid][0]

    print("Processing " + guid + "... ", end="")
    sys.stdout.flush()

    root = ET.Element(guid)

    with urllib.request.urlopen(url) as f:
        output = csv.DictReader(io.StringIO(f.read().decode("utf-8")), delimiter='\t')
        for product in output:
            product_xml = ET.SubElement(root, guids[guid][1])
            for key, value in product.items():
                product_xml.set(key, value)

    dom = xml.dom.minidom.parseString(ET.tostring(root).decode("utf-8"))

    f = open(guid + ".xml", "w")
    f.write(dom.toprettyxml())
    f.close()

    print("done")

# git diff --name-only 402dd32100394f66a39bdd852ee0b4e61442ab5a..
