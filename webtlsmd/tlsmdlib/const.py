## TLS Motion Determination (TLSMD)
## Copyright 2002-2006 by TLSMD Development Group (see AUTHORS file)
## This code is part of the TLSMD distribution and governed by
## its license.  Please see the LICENSE file that should have been
## included as part of this package.
"""Program constants
"""
from mmLib import Constants

## unreasonably small T/L eigenvalues B <= 0.01
TSMALL = 0.1 * Constants.B2U

## L RMSD <= 0.1 DEG
LSMALL = (0.1)**2 * Constants.DEG2RAD2

## mainchain atom definitions
AMINO_ACID_MAINCHAIN_ATOMS = ["N", "CA", "C", "O", "CB"]
NUCLEIC_ACID_MAINCHAIN_ATOMS = ["P", "O5*", "C5*", "C4*", "C3*", "O3*"]
MAINCHAIN_ATOMS = AMINO_ACID_MAINCHAIN_ATOMS + NUCLEIC_ACID_MAINCHAIN_ATOMS
MAINCHAIN_ATOM_DICT = {}
for res_name in MAINCHAIN_ATOMS:
    MAINCHAIN_ATOM_DICT[res_name] = True
    


