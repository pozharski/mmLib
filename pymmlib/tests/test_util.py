from __future__ import generators
import os
import sys
import re
from mmLib.mmTypes import *
"""Misc. testing utility code code common to the test programs.
"""

pdb_regex = ("[\w+\.]+pdb",
             "[\w\.]+pdb\.gz",
             "pdb[\w\.]+Z",
             "pdb[\w\.]+gz")

cif_regex = ("[\w\.]+cif",
             "[\w\.]+cif\.Z",
             "[\w\.]+cif\.gz")

all_regex = pdb_regex + cif_regex

def my_walk(path):
    """All Python's path walk functions suck.
    """
    if os.path.isfile(path):
        yield path
    elif os.path.isdir(path):
        for x in os.listdir(path):
            for y in my_walk(os.path.join(path, x)):
                yield y

def walk(path, start_path = None, regex_args = ()):
    """Iterate over all files rooted at path containing the substring
    in the filename, including extentions.
    """
    re_list = [re.compile(x) for x in regex_args]

    for pathx in my_walk(path):
        (dir, filename) = os.path.split(pathx)

        do_yield = False

        if start_path != None:
            if start_path == pathx:
                start_path = None
            else:
                continue

        for rex in re_list:
            match = rex.match(filename)
            if match:
                do_yield = True
                break

        if do_yield:
            yield pathx
            
def walk_pdb(path, start_path = None):
    return walk(path, start_path=start_path, regex_args=pdb_regex)

def walk_cif(path, start_path = None):
    return walk(path, start_path=start_path, regex_args=cif_regex)

def walk_pdb_cif(path, start_path = None):
    return walk(path, start_path=start_path, regex_args=all_regex)

def pdb_stats(path):
    re_model = re.compile("^MODEL\s+(\d+).*")
    re_atom = re.compile("^(?:ATOM|HETATM)\s*(\d+).*")

    model = 1
    serial_map = {}
    stats = {"atoms" : 0}

    for ln in OpenFile(path, "r").readlines():

        ## change model
        m = re_model.match(ln)
        if m != None:
            model = m.group(1)
            continue

        ## count atoms
        m = re_atom.match(ln)
        if m != None:
            stats["atoms"] += 1

            ser = m.group(1)
            ser = "%s-%s" % (ser, model)

            if serial_map.has_key(ser):
                print "DUPLICATE ID"
                print "[1]",serial_map[ser]
                print "[2]",ln
                sys.exit(1)
            else:
                serial_map[ser] = ln

    return stats

def cif_stats(path):
    re_atom = re.compile("^(?:ATOM|HETATM)\s+(\d+)\s+.*")

    atom_site_ids = {}    
    start_counting_atoms = False
    stats = {"atoms" : 0}

    for ln in OpenFile(path, "r").readlines():

        if ln.startswith("_atom_site."):
            start_counting_atoms = True

        if not start_counting_atoms:
            continue

        ## count atoms
        m = re_atom.match(ln)
        if m != None:
            stats["atoms"] += 1
            aid = m.group(1)

            if atom_site_ids.has_key(aid):
                print "DUPLICATE ID"
                print "[1]",atom_site_ids[aid]
                print "[2]",ln
                sys.exit(1)
            else:
                atom_site_ids[aid] = ln
        
    return stats


if __name__ == "__main__":

    for pathx in walk_pdb_cif("/home/jpaint/pdb"):

        if pathx.endswith(".Z") or pathx.endswith(".gz"):
            x = "gunzip %s" % (pathx)
            print "CMD: ",x
            os.system(x)
            
            if pathx.endswith(".Z"):
                pathx = pathx[:-2]
            else:
                pathx = pathx[:-3]

        (dir, filename) = os.path.split(pathx)

        
        dest = os.path.join("/home/jpaint/pdball", filename)

        if not os.path.isfile(dest):
            x = "cp %s %s" % (pathx, dest)
            print "CMD: ",x
            os.system(x)
