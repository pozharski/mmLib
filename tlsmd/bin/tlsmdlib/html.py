## TLS Minimized Domains (TLSMD)
## Copyright 2002 by TLSMD Development Group (see AUTHORS file)
## This code is part of the TLSMD distrobution and governed by
## its license.  Please see the LICENSE file that should have been
## included as part of this package.

###############################################################################
## Report Directory Generation
##

import popen2

## Python Imaging Library imports
import Image
import ImageDraw

## mmLib
from mmLib.Colors         import *
from mmLib.Viewer         import *
from mmLib.R3DDriver      import Raster3DDriver

from misc                 import *

## program paths
GNUPLOT_PATH = "gnuplot"
GNUPLOT_FONT = "/home/jpaint/tlsmd/fonts/LucidaSansOblique.ttf"
GNUPLOT_FONT_SIZE = "8"

JMOL_DIR     = "../../../jmol"

## constants

## the pixel width of the TLS visualization rendered raytraces
VIS_WIDTH = 400

## pixel size of the gnuplot generated images
GNUPLOT_WIDTH = 600

## target pixel width, height, and spacing of sequence
## alignment plots
ALIGN_TARGET_WIDTH = 500
ALIGN_HEIGHT       = 15
ALIGN_SPACING      = 5

## the JMol viewer is a square window, generated with
## this pixel size
JMOL_SIZE = 600

## the isoprobability contour level for all
## visualizations
ADP_PROB = 85

## text blocks
MOTION_ANALYSIS_TEXT = """\
This analysis explicity shows how each protein chain can be split into
multiple TLS groups using one to twenty adjecent, continous groups
along the chain sequence.  It goes on to analyize the implied rigid body
translational and rotatational motion of each group, as well as its
quality of fit to the refined atomic displacement parameters (B-factors).
"""

MULTI_CHAIN_ALIGNMENT_TEXT = """\
When multiple chains are present in your input structure, a side-by-side
sequence alignment is generated to show how the TLS group selection of one
chain aligns with the selection the other chains.  This analysis is only
meaningful when there are multiple chains of the same sequence in the
asymetric unit.
"""

REFINEMENT_PREP_TEXT = """\
The macromolecular refinement program Refmac5 from CCP4 implements a
refinement mode where a TLS description can be added to individual isotropic
temperature factors.  Traditionally, one TLS group is assigned for each
chain because there has been no technique for selecting multiple TLS groups
from the crystallographic data.  However, this is the calculation TLSMD
performs.  By using this TLSMD refinement preperation, you can choose
the number of TLS groups to use per chain, and generate a input PDB
and TLSIN file for refinement using Refmac5.
"""

LSQR_CAPTION = """\
TLSMD selects TLS groups by the minimization of a residual function.
This plot shows the value of the residual as a function of the number
of TLS groups allowed to be used in in the minimization.  Using a given
number of TLS groups, the residual value in the plot above is the lowest
found when all possible choices of protein chain continous TLS groups are
considered.  The details of these TLS groups are analyzed below.
"""

SEG_ALIGN_CAPTION = """\
This plot shows the location along the protein sequence of the
optimal TLS group segments, and how those segments align with
the optimal TLS group segments as the number of TLS groups used
increases.
"""

TRANSLATION_GRAPH_CAPTION = """\
This graph shows the TLS group translational displacement magnitude
of the three principal components of the reduced T tensor at a
isoprobability magnitude of 85%.  The line colors are the same as
those used for the TLS groups in the structure visualization.
"""

LIBRATION_GRAPH_CAPTION = """\
This graph shows the displacement caused by the three TLS group screw axes
on the mainchain atoms of the protein.  The screw displacement axes are
calculated in terms of a Gaussian variance-covariance tensor, and displacment
magnituce is shown at a 85% isoprobability magnitude like the translational
displacement.  Protein segments with hinge-like flexibility show up as peaks in
this graph.
"""

FIT_GRAPH_CAPTION = """\
This graph assesses the quality of the TLS prediction for each TLS group
spanning the residue chain by graphing the difference in the refined (input)
mainchain atom B factors from the TLS model predicted B factors.  If the
TLS model was a perfect fit to the input structure data, this would be
a line at 0.0.
"""



def rgb_f2i(rgb):
    """Transforms the float 0.0-1.0 RGB color values to
    integer 0-255 RGB values.
    """
    r, g, b = rgb
    ri = int(255.0 * r)
    gi = int(255.0 * g)
    bi = int(255.0 * b)
    return (ri, gi, bi)


def calc_inertia_tensor(atom_iter):
    """Calculate moment of inertia tensor at the centroid
    of the atoms.
    """
    al              = AtomList(atom_iter)
    centroid        = al.calc_centroid()

    I = zeros((3,3), Float)
    for atm in al:
        x = atm.position - centroid

        I[0,0] += x[1]**2 + x[2]**2
        I[1,1] += x[0]**2 + x[2]**2
        I[2,2] += x[0]**2 + x[1]**2

        I[0,1] += - x[0]*x[1]
        I[1,0] += - x[0]*x[1]
        
        I[0,2] += - x[0]*x[2]
        I[2,0] += - x[0]*x[2]

        I[1,2] += - x[1]*x[2]
        I[2,1] += - x[1]*x[2]

    evals, evecs = eigenvectors(I)

    elist = [(evals[0], evecs[0]),
             (evals[1], evecs[1]),
             (evals[2], evecs[2])]

    elist.sort()

    R = array((elist[0][1], elist[1][1], elist[2][1]), Float)

    ## make sure the tensor uses a right-handed coordinate system
    if allclose(determinant(R), -1.0):
        I = identity(3, Float)
        I[0,0] = -1.0
        R = matrixmultiply(I, R)
    assert allclose(determinant(R), 1.0)

    return centroid, R


def calc_orientation(struct, chain):
    """Orient the structure based on a moment-of-intertia like tensor
    centered at the centroid of the structure.
    """
    ori = {}

    def iter_protein_atoms(sobjx):
        for fragx in sobjx.iter_amino_acids():
            for atmx in fragx.iter_atoms():
                yield atmx
                
    str_centroid, str_R = calc_inertia_tensor(iter_protein_atoms(struct))
    chn_centroid, chn_R = calc_inertia_tensor(iter_protein_atoms(chain))

    ## now calculate a rectangular box
    min_x = 0.0
    max_x = 0.0
    min_y = 0.0
    max_y = 0.0
    min_z = 0.0
    max_z = 0.0

    for atm in chain.iter_all_atoms():
        x     = matrixmultiply(str_R, atm.position - chn_centroid)
        min_x = min(min_x, x[0])
        max_x = max(max_x, x[0])
        min_y = min(min_y, x[1])
        max_y = max(max_y, x[1])
        min_z = min(min_z, x[2])
        max_z = max(max_z, x[2])

    ## add slop splace around the edges
    slop   = 2.0

    min_x -= slop
    max_x += slop
    min_y -= slop
    max_y += slop
    min_z -= slop
    max_z += slop

    ## calculate the zoom based on a target width
    target_pwidth = VIS_WIDTH

    hwidth  = max(abs(min_x),abs(max_x))
    hheight = max(abs(min_y),abs(max_y))
    pheight = target_pwidth * (hheight / hwidth)
    hzoom   = 2.0 * hwidth

    ori["R"]        = str_R
    ori["centroid"] = chn_centroid
    ori["pwidth"]   = target_pwidth
    ori["pheight"]  = pheight 
    ori["hzoom"]    = hzoom

    ## calculate near, far clipping blane
    ori["near"] = max_z
    ori["far"]  = min_z
    
    return ori


class FragmentID(object):
    """A fragment ID class acts a lot like a string, but separates the
    res_seq and icode internally.
    """
    def __init__(self, frag_id):
        self.res_seq = 1
        self.icode = ""
        try:
            self.res_seq = int(frag_id)
        except ValueError:
            try:
                self.res_seq = int(frag_id[:-1])
            except ValueError:
                pass
            else:
                self.icode = frag_id[-1]
    def __str__(self):
        return str(self.res_seq) + self.icode
    def __lt__(self, other):
        assert isinstance(other, FragmentID)
        return (self.res_seq, self.icode) < (other.res_seq, other.icode)
    def __le__(self, other):
        assert isinstance(other, FragmentID)
        return (self.res_seq, self.icode) <= (other.res_seq, other.icode)
    def __eq__(self, other):
        assert isinstance(other, FragmentID)
        return (self.res_seq, self.icode) == (other.res_seq, other.icode)
    def __ne__(self, other):
        assert isinstance(other, FragmentID)
        return (self.res_seq, self.icode) != (other.res_seq, other.icode)
    def __gt__(self, other):
        assert isinstance(other, FragmentID)
        return (self.res_seq, self.icode) > (other.res_seq, other.icode)
    def __ge__(self, other):
        assert isinstance(other, FragmentID)
        return (self.res_seq, self.icode) >= (other.res_seq, other.icode)



class GNUPlot(object):
    """Provides useful methods for subclasses which need to run gnuplot.
    """
    def gnuplot_mkscript(self, template, replace_dict):
        """Replaces key strings in the template with the values in
        the replac_dict.  Returns the modificed template.
        """
        for key, val in replace_dict.items():
            template = template.replace(key, val)
        return template
    
    def gnuplot_run(self, script, basename=None):
        """Runs gnuplot
        """
        ## if a basename is given, then write the GnuPlot script
        ## as a file
        if basename!=None:
            open("%s.plot" % (basename), "w").write(script)
        
        ## run gnuplot
        stdout, stdin, stderr = popen2.popen3((GNUPLOT_PATH, ), 32768)
        stdin.write(script)
        stdin.close()

        #stdout.read()
        stdout.close()
        #stderr.read()
        stderr.close()
        

_LSQR_VS_TLS_SEGMENTS_TEMPLATE = """\
set xlabel "Number of TLS Segments"
set ylabel "Residual"
set style line 1 lw 3
set term png enhanced font "<font>" <fontsize>
set output "<pngfile>"
set title "<title>"
plot "<txtfile>" using 1:2 title "Minimization (Weighted) Residual" ls 1 with linespoints
"""
        
class LSQR_vs_TLS_Segments_Plot(GNUPlot):
    def __init__(self, chainopt):
        ## generate data and png paths
        basename = "%s_CHAIN%s_RESID" % (
            chainopt["struct_id"] , chainopt["chain_id"])

        self.txt_path = "%s.txt" % (basename)
        self.png_path = "%s.png" % (basename)

        fil = open(self.txt_path, "w")
        for h, tlsopt in chainopt["paths"]:
            fil.write("%10d %f\n" % (h, tlsopt.residual))
        fil.close()

        ## modify script template
        script = _LSQR_VS_TLS_SEGMENTS_TEMPLATE
        script = script.replace("<font>", GNUPLOT_FONT)
        script = script.replace("<fontsize>", GNUPLOT_FONT_SIZE)
        script = script.replace("<txtfile>", self.txt_path)
        script = script.replace("<pngfile>", self.png_path)
        script = script.replace(
            "<title>", "Least Squares Residual vs. Number of TLS "\
            "Segments for %s Chain %s " % (
            chainopt["struct_id"], chainopt["chain_id"]))

        self.gnuplot_run(script, basename)



_LSQR_VS_TLS_SEGMENTS_ALL_CHAINS_TEMPLATE = """\
set xlabel "Number of TLS Segments"
set ylabel "Minimization (Weighted) LSQR Residual"
set style line 1 lw 3
set term png enhanced font "<font>" <fontsize>
set output "<pngfile>"
set title "<title>"
"""

class LSQR_vs_TLS_Segments_All_Chains_Plot(GNUPlot):
    def __init__(self, chainopt_list):
        struct_id = chainopt_list[0]["struct_id"]
        
        ## generate data and png paths
        basename = "%s_RESID" % (struct_id)
        self.png_path = "%s.png" % (basename)

        ## prepare gnuplot script
        script = _LSQR_VS_TLS_SEGMENTS_ALL_CHAINS_TEMPLATE
        script = script.replace("<font>", GNUPLOT_FONT)
        script = script.replace("<fontsize>", GNUPLOT_FONT_SIZE)
        script = script.replace("<pngfile>", self.png_path)
        script = script.replace(
            "<title>", "Least Squares Residual vs. Number of TLS "\
            "Segments of %s" % (struct_id))

        ## re-use the data files of LSQRvsNTLS from the individual
        ## graphs; to do this the filenames have to be re-constructed
        plist = []
        for chainopt in chainopt_list:
            chain_id = chainopt["chain_id"]
            filename = "%s_CHAIN%s_RESID.txt" % (struct_id, chain_id)
            x = '"%s" using 1:2 title "Chain %s" ls 1 with linespoints' % (
                filename, chain_id)
            plist.append(x)
        script += "plot " + string.join(plist, ",\\\n\t") + "\n"

        self.gnuplot_run(script, basename)


_TRANSLATION_ANALYSIS_TEMPLATE = """\
set xlabel "Residue"
set xrange [<xrng1>:<xrng2>]
set ylabel "Angstroms Displacement"
set term png enhanced font "<font>" <fontsize>
set output "<pngfile>"
set title "<title>"
"""

class TranslationAnalysis(GNUPlot):
    def __init__(self, chainopt, tlsopt, ntls):      
        basename = "%s_CHAIN%s_NTLS%s_TRANSLATION" % (
            chainopt["struct_id"], chainopt["chain_id"], ntls)

        self.png_path = "%s.png" % (basename)

        data_file_list = []
        for tls in tlsopt.tls_list:
            filename = self.write_data_file(chainopt, tls)
            data_file_list.append(filename)

        script = _TRANSLATION_ANALYSIS_TEMPLATE
        script = script.replace("<font>", GNUPLOT_FONT)
        script = script.replace("<fontsize>", GNUPLOT_FONT_SIZE)
        script = script.replace("<fontsize>", GNUPLOT_FONT_SIZE)

        script = script.replace("<xrng1>", tlsopt.tls_list[0]["frag_id1"])
        script = script.replace("<xrng2>", tlsopt.tls_list[-1]["frag_id2"])
        
        script = script.replace("<pngfile>", self.png_path)
        script = script.replace(
            "<title>",
            "Translation Displacment Analysis of Atoms for "\
            "%d TLS Groups" % (ntls))

        ## line style
        ls = 0
        for tls in tlsopt.tls_list:
            ls += 1
            script += 'set style line %d lc rgb "%s" lw 3\n' % (
                ls, tls["color"]["rgbs"])

        ## plot list
        plist = []
        ls = 0
        for filename in data_file_list:
            ls += 1
            for n in (2,3,4):
                x = '"%s" using 1:%d notitle ls %d with lines' % (
                    filename, n, ls)
                plist.append(x)

        script += "plot " + string.join(plist, ",\\\n\t") + "\n"
           
        self.gnuplot_run(script, basename)

    def write_data_file(self, chainopt, tls):
        """Generate the data file and return the filename.
        """
        tls_group = tls["tls_group"]
        tls_info  = tls["tls_info"]

        ## generate a sorted list of fragment IDs from the TLS group atoms
        fid_list = []
        for atm in tls_group:
            fid = FragmentID(atm.fragment_id)
            if fid not in fid_list:
                fid_list.append(fid)
        fid_list.sort()

        ## determine Tr translational eigenvalues
        evals = eigenvalues(tls_info["rT'"])
        t1    = GAUSS3C[ADP_PROB] * math.sqrt(evals[0])
        t2    = GAUSS3C[ADP_PROB] * math.sqrt(evals[1])
        t3    = GAUSS3C[ADP_PROB] * math.sqrt(evals[2])
        
        ## write data file
        filename  = "%s_CHAIN%s_TLS%s_%s_TRANSLATION.txt" % (
            chainopt["struct_id"], chainopt["chain_id"],
            tls["frag_id1"], tls["frag_id2"])

        fil = open(filename, "w")
        for fid in fid_list:
            fil.write("%s %f %f %f\n" % (fid, t1, t2, t3))
        fil.close()

        return filename



_LIBRATION_ANALYSIS_TEMPLATE = """\
set xlabel "Residue"
set ylabel "Angstroms Displacement"
set term png enhanced font "<font>" <fontsize>
set output "<pngfile>"
set title "<title>"
"""

class LibrationAnalysis(GNUPlot):
    def __init__(self, chainopt, tlsopt, ntls):      
        
        basename = "%s_CHAIN%s_NTLS%s_LIBRATION" % (
            chainopt["struct_id"], chainopt["chain_id"], ntls)

        self.png_path = "%s.png" % (basename)

        data_file_list = []
        for tls in tlsopt.tls_list:
            filename = self.write_data_file(chainopt, tls)
            data_file_list.append(filename)

        script = _LIBRATION_ANALYSIS_TEMPLATE
        script = script.replace("<font>", GNUPLOT_FONT)
        script = script.replace("<fontsize>", GNUPLOT_FONT_SIZE)
        script = script.replace("<pngfile>", self.png_path)
        script = script.replace(
            "<title>",
            "Screw Displacment Analysis of backbone Atoms using "\
            "%d TLS Groups" % (ntls))

        ## line style
        ls = 0
        for tls in tlsopt.tls_list:
            ls += 1
            script += 'set style line %d lc rgb "%s" lw 3\n' % (
                ls, tls["color"]["rgbs"])

        ## plot list
        plist = []
        ls = 0
        for filename in data_file_list:
            ls += 1
            for n in (4,5,6):
                x = '"%s" using 3:%d smooth bezier '\
                    'notitle ls %d with lines' % (
                    filename, n, ls)
                plist.append(x)

        script += "plot " + string.join(plist, ",\\\n\t") + "\n"
           
        self.gnuplot_run(script, basename)

    def write_data_file(self, chainopt, tls):
        """Generate the data file and return the filename.
        """
        tls_group = tls["tls_group"]
        tls_info  = tls["tls_info"]
        cor       = tls_info["COR"]

        frag_dict = {}
        for atm in tls_group:
            if atm.name in ["N","CA","C"]:
                frag_dict[atm] = [FragmentID(atm.fragment_id), 0.0, 0.0, 0.0] 
                
        for n, Lx_val, Lx_vec, Lx_rho, Lx_pitch in [
            (1, "L1_eigen_val", "L1_eigen_vec", "L1_rho", "L1_pitch"),
            (2, "L2_eigen_val", "L2_eigen_vec", "L2_rho", "L2_pitch"),
            (3, "L3_eigen_val", "L3_eigen_vec", "L3_rho", "L3_pitch") ]:

            Lval   = tls_info[Lx_val]
            Lvec   = tls_info[Lx_vec]
            Lrho   = tls_info[Lx_rho]
            Lpitch = tls_info[Lx_pitch]

            for atm, frag_rec in frag_dict.items():
                d = calc_LS_displacement(
                    cor, Lval, Lvec, Lrho, Lpitch, atm.position, ADP_PROB)
                frag_rec[n] = length(d)

        ## write data file
        filename  = "%s_CHAIN%s_TLS%s_%s_LIBRATION.txt" % (
            chainopt["struct_id"], chainopt["chain_id"],
            tls["frag_id1"], tls["frag_id2"])

        fil = open(filename, "w")

        listx = []
        for atm, frag_rec in frag_dict.items():
            if   atm.name=="N":  i = 1
            elif atm.name=="CA": i = 2
            elif atm.name=="C":  i = 3
            listx.append((frag_rec[0], i, frag_rec[1],frag_rec[2],frag_rec[3]))
        listx.sort()

        for frag_rec in listx:
            fid, i, d1, d2, d3 = frag_rec

            try:
                fidf = float(str(fid))
            except ValueError:
                continue

            if i==1: fidf -= 0.33
            if i==3: fidf += 0.33
            
            fil.write("%s %1d %f %f %f %f\n" % (fid, i, fidf, d1, d2, d3))

        fil.close()

        return filename

     

_FIT_ANALYSIS_TEMPLATE = """\
set xlabel "Residue"
set ylabel "B_{obs} - B_{calc}"
set term png enhanced font "<font>" <fontsize>
set output "<pngfile>"
set title "<title>"
"""

class FitAnalysis(GNUPlot):
    def __init__(self, chainopt, tlsopt, ntls):
        
        basename = "%s_CHAIN%s_NTLS%s_FIT" % (
            chainopt["struct_id"], chainopt["chain_id"], ntls)

        self.png_path = "%s.png" % (basename)

        data_file_list = []
        for tls in tlsopt.tls_list:
            filename = self.write_data_file(chainopt, tls)
            data_file_list.append(filename)

        script = _FIT_ANALYSIS_TEMPLATE
        script = script.replace("<font>", GNUPLOT_FONT)
        script = script.replace("<fontsize>", GNUPLOT_FONT_SIZE)
        script = script.replace("<pngfile>", self.png_path)
        script = script.replace(
            "<title>",
            "TLS Model Fit Analysis of Backbone Atoms for "\
            "%d TLS Groups" % (ntls))

        ## line style
        ls = 0
        for tls in tlsopt.tls_list:
            ls += 1
            script += 'set style line %d lc rgb "%s" lw 3\n' % (
                ls, tls["color"]["rgbs"])

        ## plot list
        plist = []
        ls = 0
        for filename in data_file_list:
            ls += 1
            x = '"%s" using 1:2 smooth bezier '\
                'notitle ls %d with lines' % (
                filename, ls)

            plist.append(x)

        script += "plot " + string.join(plist, ",\\\n\t") + "\n"
           
        self.gnuplot_run(script, basename)

    def write_data_file(self, chainopt, tls):
        """Generate the data file and return the filename.
        """
        tls_group = tls["tls_group"]
        tls_info  = tls["tls_info"]

        filename  = "%s_CHAIN%s_TLS%s_%s_FIT.txt" % (
            chainopt["struct_id"], chainopt["chain_id"],
            tls["frag_id1"], tls["frag_id2"])

        fil = open(filename, "w")

        for atm, U in tls_group.iter_atm_Utls():
            if atm.name not in ["N", "CA", "C"]:
                continue

            utls_temp_factor = U2B * trace(U)/3.0
            bdiff = atm.temp_factor - utls_temp_factor
            
            try:
                fidf = float(str(atm.fragment_id))
            except ValueError:
                continue

            if atm.name=="N": fidf -= 0.33
            if atm.name=="C": fidf += 0.33

            fil.write("%f %f\n" % (fidf, bdiff))

        fil.close()

        return filename



_UISO_VS_UTLSISO_HISTOGRAM_TEMPLATE = """\
set xlabel "B_{obs} - B_{calc}"
set ylabel "Number of Atoms"
set style line 1 lc rgb "<rgb>" lw 3
set term png enhanced font "<font>" <fontsize>
set output "<pngfile>"
set title "<title>"
plot "<txtfile>" using 1:2 ls 1 notitle with histeps
"""

class UIso_vs_UtlsIso_Hisotgram(GNUPlot):
    def __init__(self, chainopt, ntls, tlsopt, tls):        
        ## generate data and png paths
        basename  = "%s_CHAIN%s_TLS%s_%s_BoBc" % (
            chainopt["struct_id"],
            chainopt["chain_id"],
            tls["frag_id1"],
            tls["frag_id2"])
        
        self.txt_path = "%s.txt" % (basename)
        self.png_path = "%s.png" % (basename)

        ## write out the data file
        tls_group = tls["tls_group"]

        ## create a histogram of (Uiso - Utls_iso)
        bdiff_min = 0.0
        bdiff_max = 0.0

        for atm, Utls in tls_group.iter_atm_Utls():
            u_tls_iso = (trace(Utls) / 3.0) * U2B
            bdiff = atm.temp_factor - u_tls_iso

            bdiff_min = min(bdiff_min, bdiff)
            bdiff_max = max(bdiff_max, bdiff)

        ## compute the bin width and range to bin over
        brange    = (bdiff_max - bdiff_min) + 2.0
        num_bins  = int(brange)
        bin_width = brange / float(num_bins)
        bins      = [0 for n in range(num_bins)]

        ## name the bins with their mean value
        bin_names = []
        for n in range(num_bins):
            bin_mean = bdiff_min + (float(n) * bin_width) + (bin_width / 2.0)
            bin_names.append(bin_mean)

        ## count the bins
        for atm, Utls in tls_group.iter_atm_Utls():
            u_tls_iso = (trace(Utls) / 3.0) * U2B
            bdiff = atm.temp_factor - u_tls_iso
            bin = int((bdiff - bdiff_min)/ bin_width)
            bins[bin] += 1

        ## write out the gnuplot input file
        fil = open(self.txt_path, "w")
        fil.write("## Histogram of atoms in the TLS group binned by\n")
        fil.write("## the difference of their isotropic tempature factors\n")
        fil.write("## from the isotropic values predicted from the TLS model.\n")
        fil.write("##\n")
        fil.write("## Structure ----------------: %s\n" % (
            chainopt["struct_id"]))
        fil.write("## Chain --------------------: %s\n" % (
            chainopt["chain_id"]))
        fil.write("## Number of TLS Groups -----: %d\n" % (ntls))
        fil.write("## TLS Group Residue Range --: %s-%s\n" % (
            tls["frag_id1"], tls["frag_id2"]))

        for i in range(len(bins)):
            fil.write("%f %d\n" % (bin_names[i], bins[i]))

        fil.close()

        ## modify script template
        script = _UISO_VS_UTLSISO_HISTOGRAM_TEMPLATE
        script = script.replace("<font>", GNUPLOT_FONT)
        script = script.replace("<fontsize>", GNUPLOT_FONT_SIZE)
        script = script.replace("<txtfile>", self.txt_path)
        script = script.replace("<pngfile>", self.png_path)

        title = "Histogram of Observed B_{iso} vs. TLS B_{iso} for TLS Group "\
                "%s%s-%s%s" % (tls["chain_id"], tls["frag_id1"],
                               tls["chain_id"], tls["frag_id2"])
        script = script.replace("<title>", title)

        script = script.replace("<rgb>", tls["color"]["rgbs"])

        self.gnuplot_run(script, basename)


class TLSSegmentAlignmentPlot(object):
    """Step 1: add all chains, generate unique list of ordered fragment ids,
               and hash all chain+frag_id->tls color
       Step 2: generate graphs
    """
    def __init__(self):
        ## bars are 15 pixels heigh
        self.pheight    = ALIGN_HEIGHT
        ## spacing pixels between stacked bars
        self.spacing    = ALIGN_SPACING
        ## background color
        self.bg_color   = rgb_f2i((1.0, 1.0, 1.0))
        
        self.frag_list     = []
        self.segmentations = []

    def add_tls_segmentation(self, tls_graph_info, ntls):
        """
        """
        ## get the list of TLS segments for the specified number of
        ## segments (ntls)
        tls_seg_desc = {}
        self.segmentations.append(tls_seg_desc)
        tls_seg_desc["tls_graph_info"] = tls_graph_info
        tls_seg_desc["ntls"]           = ntls
        tls_seg_desc["tlsopt"]        = tls_graph_info["segmentation"][ntls]
        
        ## update the master fragment_list
        self.update_frag_list(
            tls_graph_info["chain"], tls_seg_desc["tlsopt"])

    def update_frag_list(self, chain, tlsopt):
        """Add any fragment_ids found in the tls segments to the master
        self.frag_list and sort it.
        """
        for tls in tlsopt.tls_list:
            segment = tls["segment"]

            for frag in segment.iter_fragments():
                fid = FragmentID(frag.fragment_id)

                if fid not in self.frag_list:
                    self.frag_list.append(fid)

        self.frag_list.sort()

    def plot(self, path):
        """Plot and write the png plot image to the specified path.
        """
        nfrag = len(self.frag_list)

        target_width = 500
        if nfrag>0:
            fw = int(round(float(ALIGN_TARGET_WIDTH) / nfrag))
        else:
            fw = 1
        fwidth = max(1, fw)

        ## calculate with pixel width/fragment
        ## adjust the width of the graph as necessary
        pheight = self.pheight
        pwidth  = fwidth * len(self.frag_list)
            
        ## calculate the totoal height of the image
        num_plots = len(self.segmentations)
        iheight = (pheight * num_plots) + (self.spacing * (num_plots-1)) 

        ## create new image and 2D drawing object
        image = Image.new("RGBA", (pwidth, iheight), self.bg_color)
        idraw = ImageDraw.Draw(image)
        idraw.setfill(True)

        ## draw plots
        for i in range(len(self.segmentations)):
            tls_seg_desc = self.segmentations[i]
            
            xo = 0
            yo = (i * pheight) + (i * self.spacing)

            self.plot_segmentation(
                idraw, pwidth, fwidth, (xo, yo), tls_seg_desc)

        image.save(path, "png")

    def plot_segmentation(self, idraw, pwidth, fwidth, offset, tls_seg_desc):
        pheight = self.pheight
        nfrag   = len(self.frag_list)

        ## x/y offsets
        xo, yo = offset
        
        ## iterate over tls segments, draw and color
        tlsopt = tls_seg_desc["tlsopt"]
        
        for tls in tlsopt.tls_list:
            fid1 = FragmentID(tls["frag_id1"])
            fid2 = FragmentID(tls["frag_id2"])

            i1 = self.frag_list.index(fid1)
            i2 = self.frag_list.index(fid2)

            x1 = i1       * fwidth
            x2 = (i2 + 1) * fwidth

            idraw.setink(tls["color"]["rgbi"])
            idraw.rectangle((x1+xo, yo, x2+xo, pheight+yo))



class Report(object):
    """Base class of HTML Report generating objects.
    """
    def html_head(self, title):
        """Header for all HTML pages.
        """
        x  = '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" '
        x += '"http://www.w3.org/TR/html4/loose.dtd">\n\n'
        
        x += '<html>\n'
        x += '<head>\n'
        x += '  <title>%s</title>\n' % (title)
        x += '  <style type="text/css" media=screen>\n'
        x += '  <!-- \n'
        x += '  BODY {background-color:white;'
        x += '        margin-left:5%;margin-right:5%;'
        x += '        border-left:5%;border-right:5%;'
        x += '        margin-top:2%;border-top:2%;}\n'
        x += '  -->\n'
        x += '  </style>\n'

        x += '</head>\n'
        x += '<body>\n'
        return x

    def html_title(self, title):
        x  = ''
        x += '<center>'
        x += '<h1>%s</h1>' % (title)
        x += '</center>'
        return x

    def html_foot(self):
        """Footer for all HTML pages.
        """
        x  = ''
        x += '<br>'
        x += '<center><small>'
        x += 'TLSMD Version v%s Released %s ' % (
            GLOBALS["VERSION"], GLOBALS["RELEASE_DATE"])
        x += 'by %s <i>%s</i>' % (GLOBALS["AUTHOR"], GLOBALS["EMAIL"])
        x += '</small></center>'
        x += '</body></html>\n'
        return x


class HTMLReport(Report):
    """Create a through HTML report it its own subdirectory.
    """
    def __init__(self, struct_tls_analysis):
        Report.__init__(self)
        
        self.struct          = struct_tls_analysis.struct
        self.struct_path     = struct_tls_analysis.struct_path
        self.struct_id       = struct_tls_analysis.struct_id
        self.chains          = struct_tls_analysis.chains

        self.page_multi_chain_alignment  = None
        self.pages_chain_motion_analysis = []
        self.page_refinement_prep        = None
        
    def write(self, report_dir):
        """Write out the TLSMD report to the given directory.
        """
        ## create new directory and move into it
        old_dir = os.getcwd()
        if not os.path.isdir(report_dir):
            os.mkdir(report_dir)
        os.chdir(report_dir)

        self.write_cwd()
        
        ## change back to original directory
        os.chdir(old_dir)

    def init_chain_optimization(self, chain):
        """Returns a dictionary with all the calculations on the tls_graph
        needed for the HTML rendering so that no calculations should be
        performed inside the html generating methods.
        """
        chainopt                 = {}
        chainopt["struct"]       = self.struct
        chainopt["struct_path"]  = self.struct_path
        chainopt["chain"]        = chain
        chainopt["struct_id"]    = self.struct_id
        chainopt["chain_id"]     = chain.chain_id
        chainopt["max_ntls"]     = 20
        chainopt["paths"]        = []
        chainopt["segmentation"] = {}

        ## calculate the maximum interesting ntls
        minimizer = chain.tls_chain_minimizer

        ## generate the minimized, segmentd TLS groups for 1 TLS
        ## group up to max_ntls and store it in chainopt["paths"]
        ntls = 0
        
        for h in range(1, chainopt["max_ntls"]+1):
            tlsopt = minimizer.calc_tls_optimization(h)
            if tlsopt==None:
                continue

            ntls = tlsopt.get_num_groups()
            chainopt["paths"].append((h, tlsopt))
            chainopt["segmentation"][h] = tlsopt
            
            ## assign a unique color to each tls group in a
            ## chain spanning set of tls groupos
            tlsi = 0
            for tls in tlsopt.tls_list:
                if tls["method"]=="TLS":
                    tls["color"] = self.get_tls_color(tlsi)
                    tlsi += 1
                else:
                    tls["color"] = self.colors[0]

        return chainopt

    def init_colors(self):
        """Generated the self.colors dictionary of colors for the report,
        and also writes thumbnail .png images of all the colors.
        """
        thumbnail_dir   = "colors"
        thumbnail_size  = (25, 25)

        ## make the thumbnail subdirectory
        if not os.path.isdir(thumbnail_dir):
            os.mkdir(thumbnail_dir)

        ## clear the colors list
        self.colors = []

        ## skip the first two colors which are black/white
        for i in range(len(COLORS)):
            cname, rgbf = COLORS[i]
            
            color = {}
            self.colors.append(color)

            color["index"] = i
            color["name"]  = cname
            color["rgbf"]  = rgbf
            color["rgbi"]  = rgb_f2i(rgbf)

            rgbs = "#%2x%2x%2x" % rgb_f2i(rgbf)
            rgbs = rgbs.replace(" ", "0")
            color["rgbs"]  = rgbs

            ## generate thumbnail image
            color["thumbnail_path"] = os.path.join(
                thumbnail_dir, "%s.png" % (color["name"]))

            img = Image.new("RGBA", thumbnail_size, color["rgbi"])
            img.save(color["thumbnail_path"], "png")

    def get_tls_color(self, tls_index):
        """Returns the color dict description for a TLS segment of the
        given index, starting at 0.
        """
        ## skip the first two colors; they are black and white
        i = tls_index + 2
        return self.colors[i]

    def write_cwd(self):
        """Write out all the files in the report.
        """
        ## write a local copy of the Structure
        self.struct_path = "%s.pdb" % (self.struct_id)
        SaveStructure(fil=self.struct_path, struct=self.struct)

        ## generate small .png images so  they can be placed in the
        ## TLS group tables to identify the TLS group tabular data
        ## with the generated visualization
        self.init_colors()

        ## all TLSGraph objects get their calculations out of the
        ## way before writing HTML
        chainopt_list = []
        for chain in self.chains:
            chainopt = self.init_chain_optimization(chain)
            chainopt_list.append(chainopt)

        ## write out all TLSGraph reports
        for chainopt in chainopt_list:
            self.write_tls_graph(chainopt)

        ## a report page comparing the tls group segments of all
        ## chains aginst eachother
        self.write_multi_chain_alignment(chainopt_list)
        self.write_refinement_prep(chainopt_list)

        ## write out index page
        self.write_index()

    def write_index(self):
        """Writes the main index.html file of the report.
        """
        fil = open("index.html","w")
        fil.write(self.html_index())
        fil.close()

    def html_index(self):
        """Generate and returns the HTML string for the main index.html
        file of the report.
        """
        title = "TLSMD Rigid Body Analysis of %s" % (self.struct_id)

        x  = ''
        x += self.html_head(title)
        x += self.html_title(title)

        ## MOTION ANALYSIS
        x += '<center>'
        x += '<h3>Motion Analysis</h3>'
        x += '</center>'
        x += '<p>%s</p>' % (MOTION_ANALYSIS_TEXT)

        for xdict in self.pages_chain_motion_analysis:
            x += '<p><a href="%s">%s</a></p>\n' % (
                xdict["href"], xdict["title"])

        ## MULTI CHAIN ALIGNMENT
        x += '<center>'
        x += '<h3>Multi-Chain Alignment</h3>'
        x += '</center>'
        x += '<p>%s</p>' % (MULTI_CHAIN_ALIGNMENT_TEXT)

        if self.page_multi_chain_alignment!=None:
            x += '<p><a href="%s">%s</a></p>\n' % (
                self.page_multi_chain_alignment["href"],
                self.page_multi_chain_alignment["title"])
        else:
            x += '<p><u>Only one chain was analyized in this '
            x += 'structure, so the multi-chain alignment analyisis '
            x += 'was not performed.'
            x += '</u></p>'

        ## REFINEMENT PREP
        x += '<center>'
        x += '<h3>TLS Refinement with CCP4 Refmac5</h3>'
        x += '</center>'
        x += '<p>%s</p>' % (REFINEMENT_PREP_TEXT)

        x += '<p><a href="%s">%s</a></p>\n' % (
            self.page_refinement_prep["href"],
            self.page_refinement_prep["title"])
            
        x += self.html_foot()
        return x

    def write_tls_graph(self, chainopt):
        """Writes the HTML report analysis of a single TLS graphed chain.
        """
        path  = "%s_CHAIN%s_ANALYSIS.html" % (
            self.struct_id, chainopt["chain_id"])

        title = "Chain %s TLS Analysis" % (chainopt["chain_id"])

        self.pages_chain_motion_analysis.append(
            {"title": title,
             "href":  path })

        fil = open(path, "w")
        fil.write(self.html_tls_graph(chainopt))
        fil.close()

        
    def html_tls_graph(self, chainopt):
        """Generates and returns the HTML string report analysis of a
        single TLS graphed chain.
        """
        title = "Chain %s TLS Analysis of %s" % (
            chainopt["chain_id"], self.struct_id)
        
        x  = self.html_head(title)
        x += self.html_title(title)
        x += '<center><a href="index.html">Back to Index</a></center>'
        x += '<br>\n'

        ## TLS Segments vs. Residual
        x += self.html_chain_lsq_residual_plot(chainopt)
        
        ## generate a plot comparing all segmentations
        x += self.html_chain_alignment_plot(chainopt)

        ## add tables for all TLS group selections using 1 TLS group
        ## up to max_ntls
        for h in range(1, chainopt["max_ntls"]+1):
            tmp = self.html_tls_graph_path(chainopt, h)
            if tmp!=None:
                x += tmp

            ## maybe this will help with the memory problems...
            import gc
            gc.collect()

        x += self.html_foot()
        return x

    def html_chain_lsq_residual_plot(self, chainopt):
        """Generates the Gnuplot/PNG image plot, and returns the HTML
        fragment for its display in a web page.
        """
        gp = LSQR_vs_TLS_Segments_Plot(chainopt)

        x  = ''
        x += '<center><h3>Chain %s Optimization Residual</h3></center>\n' % (
            chainopt["chain_id"])

        x += '<center>'
        x += '<table>'
        x += '<tr><td align="center">'
        x += '<img src="%s" alt="LSQR Plot">' % (gp.png_path)
        x += '</td></tr>'
        x += '<tr><td><p>%s</p></td></tr>' % (LSQR_CAPTION)
        x += '</table>'
        x += '</center>'
        
        return x

    def html_chain_alignment_plot(self, chainopt):
        """generate a plot comparing all segmentations
        """
        plot = TLSSegmentAlignmentPlot()
        
        for ntls, tlsopt in chainopt["paths"]:
            plot.add_tls_segmentation(chainopt, ntls)

        ## create filename for plot PNG image file
        plot_path = "%s_CHAIN%s_ALIGN.png" % (
            self.struct_id, chainopt["chain_id"])
        
        plot.plot(plot_path)

        x  = ''
        x += '<center><h3>Chain %s TLS Segment Sequence '\
             'Alignment</h3></center>\n' % (chainopt["chain_id"])
        
        x += '<center>'
        x += '<table border="1">'
        x += '<tr><th>Num. TLS Groups</th>'
        x += '<th>Chain %s Sequence Alignment</th></tr>'% (chainopt["chain_id"])
        x += '<tr>'
        
        x += '<td align="right">'
        x += '<table border="0" cellspacing="0" cellpadding="0">'

        for ntls, tlsopt in chainopt["paths"]:
            x += '<tr><td align="right" valign="middle" height="20">'\
                 '<font size="-20">'\
                 '<a href="#NTLS%d">%d</a>'\
                 '</font></td></tr>' % (ntls, ntls)

        x += '</table>'
        x += '</td>'

        x += '<td><img src="%s" alt="Sequence Alignment Plot"></td>' % (
            plot_path)

        x += '</tr>'
        x += '</table>'
        x += '</center>'

        x += '<p>%s</p>' % (SEG_ALIGN_CAPTION)
        
        return x

    def html_tls_graph_path(self, chainopt, ntls):
        """Generates the HTML table describing the path (set of tls groups)
        for the given number of segments(h, or ntls)
        """
        ## select the correct TLSChainDescription() for the number of ntls
        if not chainopt["segmentation"].has_key(ntls):
            return None

        tlsopt = chainopt["segmentation"][ntls]

        ## write out PDB file
        self.write_tls_pdb_file(chainopt, tlsopt, ntls)

        ## Raster3D Image
        pml_path, png_path = self.raster3d_render_tls_graph_path(
            chainopt, tlsopt, ntls)

        ## JMol Viewer Page
        jmol_path = self.jmol_html(chainopt, tlsopt, ntls)

        ## tlsout file
        tlsout_path = self.write_tlsout_file(chainopt, tlsopt, ntls)

        ## detailed analyisis of all TLS groups
        report = ChainNTLSAnalysisReport(chainopt, tlsopt, ntls)
        analysis_path = report.url

        f1 = '<font size="-5">'
        f2 = '</font>'

        x  = ''
        x += '<center style="page-break-before: always">\n'
        x += '<h3><a name="NTLS%d">'\
             'Optimal TLS Group Selection using %d Groups</a></h3>\n' % (
            ntls, ntls)

        ## navigation links
        x += '<a href="." onClick="'\
             'window.open('\
             '&quot;%s&quot;,'\
             '&quot;&quot;,'\
             '&quot;width=%d,height=%d,screenX=10,'\
             'screenY=10,left=10,top=10&quot;);'\
             'return false;">View with JMol</a>' % (
            jmol_path, JMOL_SIZE, JMOL_SIZE)

        x += '&nbsp;&nbsp;&nbsp;&nbsp;'
        x += '<a href="%s">More Info...</a>' % (analysis_path)
        x += '&nbsp;&nbsp;&nbsp;&nbsp;'
        x += '<a href="%s">TLSOUT File</a>' % (tlsout_path)

        x += '</center>\n'

        ## raytraced image
        x += '<center><img src="%s" alt="iAlt"></center><br>\n' % (png_path)

        ## TLS group table
        x += '<table width="100%" border=1>\n'

        x += '<tr>\n'
        x += '<th align="center" colspan="12">'
        x += 'Analysis with %d TLS Groups' % (ntls)
        x += '</th>\n'
        x += '</tr>\n'

        x += '<tr>\n'
        x += '<th colspan="6">Input Structure</th>\n'
        x += '<th colspan="6">TLS Predictions</th>\n'
        x += '</tr>\n'

        x += ' <tr align="left">\n'
        x += '  <th>%sColor%s</th>\n' % (f1, f2)
        x += '  <th>%sSegment%s</th>\n' % (f1, f2)
        x += '  <th>%sResidues%s</th>\n' % (f1, f2)
        x += '  <th>%sAtoms%s</th>\n'  % (f1, f2)
        x += '  <th>%s&#60;B&#62;%s</th>\n'  % (f1, f2)
        x += '  <th>%s&#60;Aniso&#62;%s</th>\n' % (f1, f2)
        x += '  <th>%sLSQR%s</th>\n' % (f1, f2)
        x += '  <th>%sLSQR/Res%s</th>\n' % (f1, f2)
        x += '  <th>%seval(T<sup>r</sup>) <var>B</var>%s</th>\n' % (f1, f2)
        x += '  <th>%seval(L) <var>DEG<sup>2</sup></var>%s</th>\n' % (f1, f2)
        x += '  <th>%s&#60;B&#62;%s</th>\n'  % (f1, f2)
        x += '  <th>%s&#60;Aniso&#62;%s</th>\n' % (f1, f2)
        x += ' </tr>\n'

        for tls in tlsopt.tls_list:
            tls_group = tls["tls_group"]
            tls_info  = tls["tls_info"]

            L     = tls_group.L * RAD2DEG2
            L_ev  = [ev for ev in eigenvalues(L)]
            L_ev.sort()
            L_ev.reverse()
            
            T_red    = tls_info["rT'"]
            T_red_ev = [ev for ev in eigenvalues(T_red)]
            T_red_ev.sort()
            T_red_ev.reverse()

            x += '<tr>\n'

            x += '<td align="center" valign="middle">'\
                 '<img src="%s" alt="%s"></td>\n' % (
                tls["color"]["thumbnail_path"],
                tls["color"]["name"])

            x += '<td>%s%s-%s%s</td>\n' % (
                f1, tls["frag_id1"], tls["frag_id2"], f2)

            x += '<td>%s%d%s</td>\n'    % (
                f1, len(tls["segment"]), f2)

            x += '<td>%s%d%s</td>\n'    % (
                f1, len(tls_group), f2)

            x += '<td>%s%5.1f%s</td>\n' % (
                f1, tls_info["exp_mean_temp_factor"], f2)

            x += '<td>%s%4.2f%s</td>\n' % (
                f1, tls_info["exp_mean_anisotropy"], f2)

            x += '<td>%s%6.4f%s</td>\n' % (
                f1, tls["lsq_residual"], f2)

            x += '<td>%s%6.4f%s</td>\n' % (
                f1, tls["lsq_residual_per_res"], f2)

            x += '<td>%s%5.1f<br>%5.1f<br>%5.1f%s</td>\n' % (
                f1,
                T_red_ev[0]*U2B,
                T_red_ev[1]*U2B,
                T_red_ev[2]*U2B,
                f2)

            x += '<td>%s%5.2f<br>%5.2f<br>%5.2f%s</td>\n' % (
                f1, L_ev[0], L_ev[1], L_ev[2], f2)

            x += '<td>%s%5.1f%s</td>\n' % (
                f1, tls_info["tls_mean_temp_factor"], f2)
            
            x += '<td>%s%4.2f%s</td>\n' % (
                f1, tls_info["tls_mean_anisotropy"], f2)

            x += '</tr>\n'

        x += '</table>\n'
        x += '<br>\n'
        
        return x

    def raster3d_render_tls_graph_path(self, chainopt, tlsopt, ntls):
        """Render TLS visualizations using Raster3D.
        """
        basename = "%s_CHAIN%s_NTLS%d" % (
            self.struct_id, chainopt["chain_id"], ntls)

        png_path = "%s.png"   % (basename)

        start_timing()
        print "Raster3D: rendering %s..." % (basename)

        struct_id = self.struct_id
        chain     = chainopt["chain"]
        chain_id  = chainopt["chain_id"]

        driver = Raster3DDriver()

        viewer = GLViewer()
        gl_struct = viewer.glv_add_struct(self.struct)

        ## orient the structure with the super-spiffy orientation algorithm
        ## which hilights the chain we are examining
        ori = calc_orientation(self.struct, chain)
        viewer.glo_update_properties(
            R         = ori["R"],
            cor       = ori["centroid"],
            zoom      = ori["hzoom"],
            near      = ori["near"],
            far       = ori["far"],
            width     = ori["pwidth"],
            height    = ori["pheight"],
            bg_color  = "White")

        ## turn off axes and unit cell visualization
        gl_struct.glo_update_properties_path(
            "gl_axes/visible", False)
        gl_struct.glo_update_properties_path(
            "gl_unit_cell/visible", False)

        ## setup base structural visualization
        for gl_chain in gl_struct.glo_iter_children():
            if not isinstance(gl_chain, GLChain):
                continue
            
            gl_chain.properties.update(
                oatm_visible       = False,
                side_chain_visible = False,
                hetatm_visible     = True,
                color              = "0.20,0.20,0.20",
                lines              = False,
                ball_stick         = True,
                ball_radius        = 0.20,
                stick_radius       = 0.20 )

            ## make chains other than the one we are analyizing visible,
            ## but pale
            if gl_chain.chain.chain_id!=chain_id:
                gl_chain.properties.update(
                    ball_radius  = 0.40,
                    stick_radius = 0.40,
                    color        = "0.9,0.9,0.9")

        ## add the TLS group visualizations
        for tls in tlsopt.tls_list:
            if tls["method"]!="TLS":
                continue
            
            tls_name = "TLS_%s_%s" % (
                tls["frag_id1"], tls["frag_id2"])
            
            gl_tls_group = GLTLSGroup(
                oatm_visible       = False,
                side_chain_visible = False,
                hetatm_visible     = True,
                adp_prob           = ADP_PROB,
                L1_visible         = True,
                L2_visible         = True,
                L3_visible         = True,
                L_axis_scale       = 2.0,
                tls_group          = tls["tls_group"],
                tls_info           = tls["tls_info"],
                tls_name           = tls_name,
                tls_color          = tls["color"]["name"])

            gl_struct.glo_add_child(gl_tls_group)

        ## set visualization: TLS traced surface
        for gl_tls_group in gl_struct.glo_iter_children():
            if not isinstance(gl_tls_group, GLTLSGroup):
                continue

            gl_tls_group.gl_atom_list.properties.update(
                trace_radius = 0.075)
            
            gl_tls_group.glo_update_properties(
                time = 0.25)

        driver.glr_set_render_png_path(png_path)
        viewer.glv_render_one(driver)
        print end_timing()

        return "", png_path

    def write_tls_pdb_file(self, chainopt, tlsopt, ntls):
        """Write out a PDB file with the TLS predicted anisotropic ADPs for
        this segmentation.
        """
        basename = "%s_CHAIN%s_NTLS%d_UTLS"  % (
            self.struct_id, chainopt["chain_id"], ntls)
        pdb_path = "%s.pdb" % (basename)

        ## temporarily set the atom temp_factor and U tensor to the Utls value
        old_temp_factor = {}
        old_U = {}
        for tls in tlsopt.tls_list:
            tls_group = tls["tls_group"]
            
            for atm, Utls in tls_group.iter_atm_Utls():
                old_temp_factor[atm] = atm.temp_factor
                old_U[atm] = atm.U

                atm.temp_factor = U2B * (trace(Utls)/3.0)
                atm.U = Utls

        SaveStructure(fil=pdb_path, struct=self.struct)

        ## restore atom temp_factor and U
        for atm, temp_factor in old_temp_factor.items():
            atm.temp_factor = temp_factor
            atm.U = old_U[atm]

    def write_tlsout_file(self, chainopt, tlsopt, ntls):
        """Writes the TLSOUT file for the segmentation.
        """
        basename = "%s_CHAIN%s_NTLS%d" % (
            self.struct_id, chainopt["chain_id"], ntls)
        tlsout_path = "%s.tlsout" % (basename)

        struct_id = self.struct_id
        chain_id  = chainopt["chain_id"]

        tls_file = TLSFile()
        tls_file.set_file_format(TLSFileFormatTLSOUT())

        for tls in tlsopt.tls_list:
            ## don't write out bypass edges
            if tls["method"]!="TLS":
                continue
            
            tls_desc = TLSGroupDesc()
            tls_file.tls_desc_list.append(tls_desc)
            
            tls_desc.set_tls_group(tls["tls_group"])
            tls_desc.add_range(
                chain_id, tls["frag_id1"],
                chain_id, tls["frag_id2"], "ALL")

        tls_file.save(open(tlsout_path, "w"))

        return tlsout_path
    
    def jmol_html(self, chainopt, tlsopt, ntls):
        """Writes out the HTML page which will display the
        structure using the JMol Applet.
        """
        jmol_path = "%s_CHAIN%s_NTLS%d_JMOL.html"  % (
            self.struct_id, chainopt["chain_id"], ntls)

        ## create the JMol script using cartoons and consisant
        ## coloring to represent the TLS groups
        js  = ''
        js += 'load %s;' % (self.struct_path)
        js += 'select *;'
        js += 'cpk off;'
        js += 'wireframe off;'
        js += 'select protein;'
        js += 'cartoon on;'

        ## loop over TLS groups and color
        for tls in tlsopt.tls_list:
            js += 'select %s-%s:%s;' % (
                tls["frag_id1"], tls["frag_id2"], tls["chain_id"])
            js += 'color [%d,%d,%d];' % (tls["color"]["rgbi"])

        ## write the HTML page to render the script in
        x  = ''
        x += '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '\
             '"http://www.w3.org/TR/html4/strict.dtd">'
        x += '<html>'
        x += '<head>'
        x += '<title>Chain %s using %d TLS Groups</title>' % (
            chainopt["chain_id"], ntls)
        x += '<script type="text/javascript" src="%s/Jmol.js">' % (JMOL_DIR)
        x += '</script>'
        x += '</head>'
        x += '<body>'
        x += '<script type="text/javascript">'
        x += 'jmolInitialize("%s");' % (JMOL_DIR)
        x += 'jmolSetAppletColor("white");'
        x += 'jmolApplet(%d, "%s");' % (JMOL_SIZE, js)
        x += '</script>'
        x += '</body>'
        x += '</html>'

        open(jmol_path, "w").write(x)
        return jmol_path

    def write_multi_chain_alignment(self, chainopt_list):
        """Write out the chain residue alignment page.
        """
        ## only write out the comparison page if there is more than one
        ## chain analyzed in the structure
        if len(chainopt_list)<2:
            return
        
        path  = "%s_CHAIN_COMP.html" % (self.struct_id)
        title = "Multi-Chain Alignment Analysis of TLS Groups"

        self.page_multi_chain_alignment = {
            "title": title,
            "href":  path }

        fil = open(path, "w")
        fil.write(self.html_multi_chain_alignment(chainopt_list))
        fil.close()
    
    def html_multi_chain_alignment(self, chainopt_list):
        """Write out all HTML/PDB/TLSIN files which compare
        chains in the structure.
        """
        title = self.page_multi_chain_alignment["title"]

        x  = self.html_head(title)
        x += self.html_title(title)

        x += '<center>'
        x += '<a href="index.html">Back to Index</a>'
        x += '</center>'
        x += '<br>\n'

        ## figure out the maximum number of ntls in all chains
        max_ntls = 0
        for chainopt in chainopt_list:
            max_ntls = max(max_ntls, chainopt["max_ntls"])

        ## generate ntls number of plots and add them to the
        ## HTML document
        for ntls in range(1, max_ntls+1):

            ## create a 2-tuple list of (chain_id, chainopt) for
            ## each chain which a a TLSMD segmentation of h groups
            seg_list = []
            for chainopt in chainopt_list:
                if chainopt["segmentation"].has_key(ntls):
                    seg_list.append((chainopt["chain_id"], 
                                     chainopt["segmentation"][ntls]))

            ## generate PDB and TLSIN files containing the TLS
            ## predicted anisotropic ADPs for all chains for the
            ## given number of tls segments
            basename    = "%s_NTLS%d"  % (self.struct_id, ntls)
            tlsout_path = "%s.tlsout" % (basename)
            pdb_path    = "%s.pdb" % (basename)

            old_temp_factor = {}
            old_U = {}

            for chain_id, tlsopt in seg_list:
                for tls in tlsopt.tls_list:
                    tls_group = tls["tls_group"]

                    for atm, Utls in tls_group.iter_atm_Utls():
                        old_temp_factor[atm] = atm.temp_factor
                        old_U[atm] = atm.U
                        atm.temp_factor = U2B * (
                            Utls[0,0] + Utls[1,1] + Utls[2,2]) / 3.0
                        atm.U = Utls

            ## save the structure file
            SaveStructure(fil=pdb_path, struct=self.struct)

            ## restore atom temp_factor and U
            for atm, temp_factor in old_temp_factor.items():
                atm.temp_factor = temp_factor
                atm.U = old_U[atm]

            ## generate the TLS segmentation alignment plot for all chains
            plot = TLSSegmentAlignmentPlot()
            chain_id_list = []

            for chainopt in chainopt_list:
                if not chainopt["segmentation"].has_key(ntls):
                    continue
                
                chain_id_list.append(chainopt["chain_id"])
                plot.add_tls_segmentation(chainopt, ntls)

            plot_path = "%s_ALIGN.png" % (basename)
            plot.plot(plot_path)

            ## write HTML
            x += '<h3>Chains Alignment using %d TLS Groups</h3>\n' % (
                ntls)

            ## plot table
            x += '<table border="1">'
            x += '<tr><th>Chain</th><th>Chain Alignment</th></tr>'
            x += '<tr>'
        
            x += '<td align="center">'
            x += '<table border="0" cellspacing="0" cellpadding="0">'

            for chain_id in chain_id_list:
                x += '<tr><td align="right" valign="middle" height="20">'\
                     '<font size="-20">%s</font></td></tr>' % (chain_id)

            x += '</table>'
            x += '</td>'

            x += '<td><img src="%s" alt="Segmentation Plot"></td>' % (
                plot_path)

            x += '</tr>'
            x += '</table>'

        x += self.html_foot()
        return x



    def write_refinement_prep(self, chainopt_list):
        """Generate form to allow users to select the number of TLS groups
        to use per chain.
        """
        path  = "%s_REFINEMENT_PREP.html" % (self.struct_id)
        title = "Generate Input Files for REFMAC5 TLS Refienment of %s" % (
            self.struct_id)
 
        self.page_refinement_prep = {
            "title": title,
            "href" : path }

        fil = open(path, "w")
        fil.write(self.html_refinement_prep(chainopt_list))
        fil.close()

    def html_refinement_prep(self, chainopt_list):
        title = self.page_refinement_prep["title"]

        x  = self.html_head(title)
        x += self.html_title(title)


        x += '<center>'
        x += '<a href="index.html">Back to Index</a>'
        x += '</center>'
        x += '<br>\n'

        x += '<form enctype="multipart/form-data" '\
             'action="%s" method="get">' % (
            GLOBALS["REFINEPREP_URL"])
        x += '<input type="hidden" name="job_id" value="%s">' % (
            GLOBALS["JOB_ID"])
        
        x += '<center><table><tr><td>'
        
        plot = LSQR_vs_TLS_Segments_All_Chains_Plot(chainopt_list)
        x += '<img src="%s" alt="LSQR Residual">' % (plot.png_path)

        x += '</td></tr><tr><td>'

        x += '<table width="100%" border="1">'
        x += '<tr><th>'
        x += '<p>Select the Number of TLS Groups per Chain</p>'
        x += '</th></tr>'

        x += '<tr><td align="center">'

        x += '<table cellspacing="5">'
        for chainopt in chainopt_list:
            chain_id = chainopt["chain_id"]
            
            x += '<tr><td>'
            x += 'Number of TLS Groups for Chain %s' % (chain_id)
            x += '</td><td>'
        
            x += '<select name="NTLS_CHAIN%s">' % (chain_id)
            for ntls in range(1, chainopt["max_ntls"]+1):
                x += '<option value="%d">%d</option>' % (ntls, ntls)
            x += '</select>'

            x += '</td></tr>'
        x += '</table>'
        
        x += '</td></tr>'

        x += '<tr><td align="right">'
        x += '<input type="submit" value="OK">'
        x += '</td></tr></table>'
        
        x += '</td></tr></table></center>'

        x += '</form>'
        
        x += self.html_foot()
        return x


class ChainNTLSAnalysisReport(Report):
    """Writes a HTML report detailing one given TLS segmentation of a chain.
    """
    def __init__(self, chainopt, tlsopt, ntls):
        Report.__init__(self)

        self.struct      = chainopt["struct"]
        self.struct_id   = chainopt["struct_id"]
        self.struct_path = chainopt["struct_path"]
        self.chain_id    = chainopt["chain_id"]

        
        self.chainopt = chainopt
        self.tlsopt = tlsopt
        self.ntls    = ntls

        self.root  = ".."
        self.dir   = "%s_CHAIN%s_NTLS%d"  % (
            self.struct_id, self.chain_id, self.ntls)
        self.index = "%s.html" % (self.dir)
        self.url   = "%s/%s" % (self.dir, self.index)

        self.write_report()

    def write_report(self):
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)
        os.chdir(self.dir)

        self.write_all_files()

        os.chdir(self.root)

    def write_all_files(self):
        """Writes analysis details of each TLS group.
        """
        title = "Chain %s Analysis using %d TLS Groups" % (
            self.chain_id, self.ntls)
        
        x  = self.html_head(title)
        x += self.html_title(title)

        x += '<center>'
        x += '<a href="index.html">Back to Index</a>'
        x += '&nbsp;&nbsp;&nbsp;&nbsp;'
        path = "%s_CHAIN%s_ANALYSIS.html" % (
            self.struct_id, self.chain_id)
        x += '<a href="%s">Back to Chain %s Analysis</a>' % (
            path, self.chain_id)
        x += '</center>'
        
        x += '<br>\n'

        x += self.html_translation_analysis()
        x += self.html_libration_analysis()
        x += self.html_fit_analysis()
        
        for tls in self.tlsopt.tls_list:
            ## don't write out bypass edges
            if tls["method"]!="TLS":
                continue
            x += self.html_tls_group_analysis(tls)

        ## write out the HTML page
        x += self.html_foot()
        open(self.index, "w").write(x)

    def html_translation_analysis(self):
        """Perform a translation analysis of the protein chain as
        spanned by the tlsopt TLS groups.
        """
        x  = ''
        x += '<center>'
        x += '<h3>Translation Analysis of T<sup>r</sup></h3>'
        x += '</center>\n'

        tanalysis = TranslationAnalysis(
            self.chainopt, self.tlsopt, self.ntls)
        
        x += '<center>'
        x += '<img src="%s" alt="Translation Analysis">' % (tanalysis.png_path)
        x += '</center>\n'
        x += '<p>%s</p>' % (TRANSLATION_GRAPH_CAPTION)
        
        return x

    def html_libration_analysis(self):
        """Perform a libration analysis of the protein chain as
        spanned by the tlsopt TLS groups.
        """
        x  = ''
        x += '<center><h3>Screw Displacment Analysis</h3></center>\n'

        libration_analysis = LibrationAnalysis(
            self.chainopt, self.tlsopt, self.ntls)

        x += '<center>'
        x += '<img src="%s" alt="Libration Analysis">' % (
            libration_analysis.png_path)
        x += '</center>\n'
        x += '<p>%s</p>' % (LIBRATION_GRAPH_CAPTION)
        
        return x

    def html_fit_analysis(self):
        """Perform a fit analysis of the protein chain as
        spanned by the tlsopt TLS groups.
        """
        x  = ''
        x += '<center><h3>Mainchain TLS Fit Analysis</h3></center>\n'

        fit_analysis = FitAnalysis(
            self.chainopt, self.tlsopt, self.ntls)
        
        x += '<center>'
        x += '<img src="%s" alt="Fit Analysis">' % (
            fit_analysis.png_path)
        x += '</center>\n'
        x += '<p>%s</p>' % (FIT_GRAPH_CAPTION)

        return x

    def html_tls_group_analysis(self, tls):
        """A complete analysis of a single TLS group output as HTML.
        """
        x  = ''
        x += '<center><h3>TLS Group Spanning Residues '\
             '%s...%s</h3></center>\n' % (
            tls["frag_id1"], tls["frag_id2"])

        ## histogrm of atomic U_ISO - U_TLS_ISO
        his = UIso_vs_UtlsIso_Hisotgram(
            self.chainopt, self.ntls, self.tlsopt, tls)

        x += '<center><img src="%s" alt="iAlt"></center>\n' % (
            his.png_path)

        return x


