## TLS Minimized Domains (TLSMD)
## Copyright 2002 by TLSMD Development Group (see AUTHORS file)
## This code is part of the TLSMD distrobution and governed by
## its license.  Please see the LICENSE file that should have been
## included as part of this package.

import os
import sys
import time
import socket
import string

import xmlrpclib
import cgitb; cgitb.enable()
import cgi

from mmLib.Structure      import *
from mmLib.FileLoader     import *
from mmLib.Extensions.TLS import *

## GLOBALS
from cgiconfig import *
webtlsmdd = xmlrpclib.ServerProxy(WEBTLSMDD, allow_none=True)


CAPTION = """\
Download this modified PDB file of your structure, and its corresponding
TLSIN file begin multi-TLS group refinement using REFMAC5.  See the
TLSMD documentation for detailed instructions.
"""


def refmac5_prep(pdbin, tlsins, pdbout, tlsout):
    os.umask(022)
    
    ## load input structure
    struct = LoadStructure(fil = pdbin)

    ## load input TLS description
    tls_file = TLSFile()
    tls_file.set_file_format(TLSFileFormatTLSOUT())
    for tlsin in tlsins:
        fil = open(tlsin, "r")
        listx = tls_file.file_format.load(fil)
        tls_file.tls_desc_list += listx

    ## generate TLS groups from the structure file
    tls_group_list = []
    for tls_desc in tls_file.tls_desc_list:
        tls_group = tls_desc.construct_tls_group_with_atoms(struct)
        tls_group.tls_desc = tls_desc
        tls_group_list.append(tls_group)

    ## shift some Uiso displacement from the TLS T tensor to the
    ## individual atoms
    for tls_group in tls_group_list:
        for atm, U in tls_group.iter_atm_Utls():
            assert min(eigenvalues(U))>0.0

        ## leave some B magnitude in the file for refinement
        (tevals, R) = eigenvectors(tls_group.T)
        tmin = min(tevals)
        T = matrixmultiply(R, matrixmultiply(tls_group.T, transpose(R)))
        T = T - (tmin * identity(3, Float))
        tls_group.T = matrixmultiply(transpose(R), matrixmultiply(T, R))

        bmin = U2B * tmin
        for atm, U in tls_group.iter_atm_Utls():
            btls = U2B * (trace(U)/3.0)
            biso = atm.temp_factor

            bnew = biso - btls - bmin
            bnew = max(0.0, bnew)

            atm.temp_factor = bnew
            atm.U = None

    ## write TLSOUT file with new tensor values
    for tls_group in tls_group_list:
        tls_desc = tls_group.tls_desc
        tls_desc.set_tls_group(tls_group)
        
    fil = open(tlsout, "w")
    tls_file.save(fil)
    fil.close()

    ## write out a PDB file with reduced temperature factors
    SaveStructure(fil=pdbout, struct=struct)


class Page(object):
    def __init__(self, form):
        self.form = form

    def html_title(self, title):
        x  = ''
        x += '<center><h1>%s</h1></center>' % (title)
        return x

    def html_head_nocgi(self, title):
        x  = ''
        x += '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" '
        x += '"http://www.w3.org/TR/html4/loose.dtd">\n\n'
        x += '<html>'
        x += '<head>'
        x += '  <title>%s</title>' % (title)
        x += '  <style type="text/css" media=screen>'
        x += '  <!-- '
        x += '  BODY { background-color: white;'
        x += '         margin-left: 5%; margin-right: 5%;'
        x += '         border-left: 5%; border-right: 5%;'
        x += '         margin-top: 2%; border-top: 2%;}'
        x += '  -->'
        x += '  </style>'
        x += '</head>'
        x += '<body>'
        return x

    def html_head(self, title):
        x = ''
        x += 'Content-Type: text/html\n\n'
        x += self.html_head_nocgi(title)
        return x

    def html_foot(self):
        x = ''
        x += '<center>'
        x += '<p><small><b>Version %s</b> Last Modified %s' % (
            VERSION, LAST_MODIFIED_DATE)
        x += ' by %s ' % (LAST_MODIFIED_BY)
        x += '<i>%s</i></small></p>' % (LAST_MODIFIED_BY_EMAIL)
        x += '</center>'
        x += '</body></html>'
        return x


class ErrorPage(Page):
    def __init__(self, form, text=None):
        Page.__init__(self, form)
        self.text = text
    
    def html_page(self):
        title = 'TLSMD: Error'
        
        x  = ''
        x += self.html_head(title)
        x += self.html_title(title)
        x += '<br>'
        x += '<center><h3>A Error Occured</h3></center>'
        if self.text!=None:
            x += self.text
        x += self.html_foot()
        return x


class RefinePrepError(Exception):
    def __init__(self, text):
        Exception.__init__(self)
        self.text = text


class RefinePrepPage(Page):
    def html_page(self):
        job_id = check_job_id(self.form)
        
        title = 'Input Files for REFMAC5 TLS Refinement'
        
        x  = ''
        x += self.html_head(title)
        x += self.html_title(title)
        x += '<br>'

        ## get the analysis directory, and make sure it exists
        analysis_dir = webtlsmdd.job_data_get(job_id, "analysis_dir")
        if not os.path.isdir(analysis_dir):
            raise RefinePrepError("Analysis Directory Not Found")

        ## extract ntls selections from CGI form
        chain_ntls = []
        for key in self.form.keys():
            if key.startswith("NTLS_CHAIN"):
                chain_id = key[-1]
                try:
                    ntls = int(self.form[key].value)
                except ValueError:
                    continue
                chain_ntls.append((chain_id, ntls))

        chain_ntls.sort()

        ## make sure there were selections
        if len(chain_ntls)==0:
            raise RefinePrepError("Form Processing Error: No Chains Selected")

        ## now create filenames
        struct_id = webtlsmdd.job_data_get(job_id, "structure_id")
        assert struct_id!=False
        assert struct_id
        
        pdbin  = "%s.pdb" % (struct_id)

        ## the per-chain TLSOUT files from TLSMD must be merged
        tlsins = []
        for chain_id, ntls in chain_ntls:
            tlsin = "%s_CHAIN%s_NTLS%d.tlsout" % (struct_id, chain_id, ntls)
            tlsins.append(tlsin)

        ## form unique pdbout/tlsout filenames
        listx = [struct_id]
        for chain_id, ntls in chain_ntls:
            listx.append("CHAIN%s" % (chain_id))
            listx.append("NTLS%d" % (ntls))
        outbase = string.join(listx, "_")
        pdbout = "%s.pdb" % (outbase)

        ## the tlsout from this program is going to be the tlsin
        ## for refinement, so it's important for the filename to have
        ## the tlsin extension so the user is not confused
        tlsout = "%s.tlsin" % (outbase)

        ## make urls for linking
        analysis_base_url = webtlsmdd.job_data_get(job_id, "analysis_base_url")
        pdbout_url = "%s/%s" % (analysis_base_url, pdbout)
        tlsout_url = "%s/%s" % (analysis_base_url, tlsout)

        os.chdir(analysis_dir)
        refmac5_prep(pdbin, tlsins, pdbout, tlsout)

        x += '<p>%s</p>' % (CAPTION)

        ## success -- make download links
        x += '<center>'
        x += '<table border="1">'
        x += '<tr>'
        x += '<td align="right"><b>PDBIN File</b></td>'
        x += '<td><a href="%s" type="text/plain">%s</a></td>' % (
            pdbout_url, pdbout)
        x += '</tr><tr>'
        x += '<td align="right"><b>TLSIN File</b></td>'
        x += '<td><a href="%s" type="text/plain">%s</a></td>' % (
            tlsout_url, tlsout)
        x += '</table>'

        x += self.html_foot()
        return x


def check_job_id(form):
    """Retrieves and confirms the job_id from a incomming form.  Returns
    None on error, or the job_id on success.
    """
    if form.has_key("job_id"):
        job_id = form["job_id"].value
        if len(job_id)<20:
            if job_id.startswith("TLSMD"):
                if webtlsmdd.job_exists(job_id):
                    return job_id
    return None


def main():
    form = cgi.FieldStorage()

    page = None
    job_id = check_job_id(form)
    if job_id==None:
        page = ErrorPage("The Job ID seems to be expired.")
    else:
        page = RefinePrepPage(form)


    try:
        print page.html_page()

    except RefinePrepError, err:
        text = '<center><p>%s</p></center>' % (err.text)
        page = ErrorPage(form, text)
        print page.html_page()

    except xmlrpclib.Fault, err:
        page = ErrorPage(form, "xmlrpclib.Fault: " +str(err))
        print page.html_page()

    except socket.error, err:
        page = ErrorPage(form, "socket.error: " + str(err))
        print page.html_page()


if __name__=="__main__":
    main()
    sys.exit(0)