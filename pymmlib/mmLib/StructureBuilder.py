## Copyright 2002 by PyMMLib Development Group (see AUTHORS file)
## This code is part of the PyMMLib distrobution and governed by
## its license.  Please see the LICENSE file that should have been
## included as part of this package.
"""Classes for building a mmLib.Structure representation of biological
macromolecules.
"""

from mmTypes   import *
from Library   import *
from Structure import *


class StructureBuilder(object):
    """Builder class for the mmLib.Structure object hierarchy.
    StructureBuilder must be subclassed with a working parse_format()
    method to implement a working builder.
    """
    def __init__(self, **args):
        ## allocate a new Structure object for building if one was not
        ## passed to the StructureBuilder
        self.struct = args.get("struct") or \
                      Structure(library = args.get("library"))

        ## what items are going to be built into the Structure graph
        ## follow up with adding structural components which depend on
        ## other components
        self.build_properties = args.get("build_properties") or ()

        ## caches used while building
        self.cache_chain = None
        self.cache_frag = None

        ## if anything goes wrong, setting self.halt=True will stop the madness
        self.halt = False
        
        ## build the structure by executing this fixed sequence of methods
        self.read_start(args.get("fil"), args.get("update_cb"))
        if not self.halt: self.read_start_finalize()
        if not self.halt: self.read_atoms()
        if not self.halt: self.read_atoms_finalize()
        if not self.halt: self.read_metadata()
        if not self.halt: self.read_metadata_finalize()
        if not self.halt: self.read_end()
        if not self.halt: self.read_end_finalize()
        ## self.struct is now built and ready for use

    def read_start(self, fil, update_cb):
        """This methods needs to be reimplemented in a functional subclass.
        This function is called with the file object (or any other object
        passed in to build a Structure from) to begin the reading process.
        This is usually used to open the source file.
        """
        pass

    def read_start_finalize(self):
        """Called after the read_start method.  Does nothing currently,
        but may be used in the future.
        """
        self.name_service_list = []

    def read_atoms(self):
        """This method needs to be reimplemented in a fuctional subclass.
        The subclassed read_atoms method should call load_atom once for
        every atom in the sturcture, and should not call any other
        load_* methods.
        """
        pass

    def load_atom(self, atm_map):
        """Called repeatedly by the implementation of read_atoms to
        load all the data for a single atom.  The data is contained
        in the atm_map argument, and is not well documented at this
        point.  Look at this function and you'll figure it out.
        """
        ## create atom object
        atm = Atom(**atm_map)

        ## survey the atom and structure and determine if the atom requres
        ## being passed to the naming service
        ## absence of requred fields
        if atm.fragment_id=="" or atm.chain_id=="":
            self.name_service_list.append(atm)
            return atm

        try:
            self.struct.add_atom(atm, True)
        except FragmentOverwrite:
            print "FragmentOverwrite: ",atm
            self.name_service_list.append(atm)
        except AtomOverwrite, err:
            print err
            self.name_service_list.append(atm)

        return atm

    def name_service(self):
        """Runs the name service on all atoms needing to be named.  This is
        a complicated function which corrects most commonly found errors and
        omitions from PDB files.
        """
        if len(self.name_service_list) == 0:
            return

        ## returns the next available chain_id in self.struct
        ## XXX: it's possible to run out of chain IDs!
        def next_chain_id(suggest_chain_id):
            if suggest_chain_id != "":
                chain = self.struct.get_chain(suggest_chain_id)
                if not chain:
                    return suggest_chain_id
            
            for chain_id in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                chain = self.struct.get_chain(chain_id)
                if not chain:
                    return chain_id
                
            warning("name_service: exhausted PDB-allowed chain ids")
            return None
        

        ## NAME SERVICE FOR POLYMER ATOMS

        ## what if we are given a list of atoms with res_name, frag_id,
        ## and model_id where the frag_id are sequental?  they can be
        ## sequental sever ways using insertion codes, but large breaks
        ## often denote chain breaks

        ## I need to handle the special case of a list of polymer residues
        ## which do not have chain_ids.   This requires a first pass over
        ## the atom list usind different rules than what I use for sorting
        ## out non-polymers

        current_polymer_type      = None
        current_polymer_model_id  = None
        current_polymer_chain_id  = None
        current_polymer_frag_id   = None
        current_polymer_res_name  = None
        current_polymer_name_dict = None
    
        polymer_model_dict = {}
        current_frag       = None
        current_frag_list  = None

        for atm in self.name_service_list[:]:
            
            ## determine the polymer type of the atom
            if self.struct.library.is_amino_acid(atm.res_name):
                polymer_type = "protein"
            elif self.struct.library.is_nucleic_acid(atm.res_name):
                polymer_type = "dna"
            else:
                ## if the atom is not a polymer, we definately have a break
                ## in this chain
                current_polymer_type      = None
                current_polymer_model_id  = None
                current_polymer_chain_id  = None
                current_polymer_frag_id   = None
                current_polymer_res_name  = None
                current_polymer_name_dict = None
                current_frag              = None
                current_frag_list         = None
                continue

            fragment_id = FragmentID(atm.fragment_id)

            ## now we deal with conditions which can terminate the current
            ## polymer chain
            if polymer_type!=current_polymer_type or \
               atm.model_id!=current_polymer_model_id or \
               atm.chain_id!=current_polymer_chain_id or \
               fragment_id<current_polymer_frag_id:
                
                current_polymer_type      = polymer_type
                current_polymer_model_id  = atm.model_id
                current_polymer_chain_id  = atm.chain_id
                current_polymer_frag_id   = FragmentID(atm.fragment_id)
                current_polymer_res_name  = atm.res_name
                current_polymer_name_dict = {atm.name: True}

                ## create new fragment
                current_frag = [atm]
                current_frag_list = [current_frag]
                
                ## create new fragment list (chain)
                try:
                    model = polymer_model_dict[atm.model_id]
                except KeyError:
                    model = [current_frag_list]
                    polymer_model_dict[atm.model_id] = model
                else:
                    model.append(current_frag_list)

                ## we have now dealt with the atom, so it can be removed
                ## from the name service list
                self.name_service_list.remove(atm)
                continue

            ## if we get here, then we know this atom is destine for the
            ## current chain, and the algorithm needs to place the atom
            ## in the current fragment, or create a new fragment for it
            ## to go into; the conditions for it going into the current
            ## fragment are: it has it have the same res_name, and its
            ## atom name cannot conflict with the names of atoms already in
            ## in the fragment
            if atm.res_name!=current_polymer_res_name or \
               current_polymer_name_dict.has_key(atm.name):
                
                current_polymer_res_name  = atm.res_name
                current_polymer_name_dict = {atm.name: True}

                ## create new fragment and add it to the current fragment list
                current_frag = [atm]
                current_frag_list.append(current_frag)
  
                ## we have now dealt with the atom, so it can be removed
                ## from the name service list
                self.name_service_list.remove(atm)
                continue

            ## okay, put it in the current fragment
            current_frag.append(atm)
            self.name_service_list.remove(atm)

        ## now assign chain_ids and add the atoms to the structure
        model_ids = polymer_model_dict.keys()
        model_ids.sort()
        model_list = [polymer_model_dict[model_id] for model_id in model_ids]

        num_chains = 0
        for frag_list in polymer_model_dict.values():
            num_chains = max(num_chains, len(frag_list))

        for chain_index in range(num_chains):
            ## get next availible chain_id
            chain_id = next_chain_id("")

            ## assign the chain_id to all the atoms in the chain
            ## TODO: check fragment_id too
            for model in model_list:
                frag_list = model[chain_index]

                for frag in frag_list:
                    for atm in frag:
                        atm.chain_id = chain_id
                        self.struct.add_atom(atm, True)

        ## free the memory used by the polymer naming service
        del polymer_model_dict
        del model_list


        
        ## NAME SERVICE FOR NON-POLYMER ATOMS
        ## cr = (chain_id, res_name)
        ##
        ## cr_dict[cr_key] = model_dict
        ##
        ## model_dict[model] = frag_list
        ##
        ## frag_list = [ frag1, frag2, frag3, ...]
        ##
        ## frag = [atm1, atm2, atm3, ...]
        
        cr_dict      = {}
        cr_key_list  = []
        
        frag_id   = None
        frag      = None
        name_dict = {}

        ## split atoms into fragments
        for atm in self.name_service_list:
            atm_id      = (atm.name, atm.alt_loc)
            atm_frag_id = (atm.model_id,
                           atm.chain_id,
                           atm.fragment_id,
                           atm.res_name)

            ## if the atom fragment id matches the current fragment id
            ## and doesn't conflict with any other atom name in the fragment
            ## then add it to the fragment
            if atm_frag_id==frag_id and not name_dict.has_key(atm_id):
                frag.append(atm)
                name_dict[atm_id] = True
                
            else:
                cr_key = (atm.chain_id, atm.res_name)
                
                ### debug
                if frag:
                    debug("name_service: fragment detected in cr=%s" % (
                        str(cr_key)))
                    for a in frag:
                        debug("  " + str(a))
                ### /debug
                
                try:
                    model_dict = cr_dict[cr_key]
                except KeyError:
                    model_dict = cr_dict[cr_key] = {}
                    cr_key_list.append(cr_key)

                try:
                    frag_list = model_dict[atm.model_id]
                except KeyError:
                    frag_list = model_dict[atm.model_id] = []

                name_dict = {atm_id: True}
                frag_id   = atm_frag_id
                frag      = [atm]
                frag_list.append(frag)

        ## free self.name_service_list and other vars to save some memory
        del self.name_service_list

        new_chain_id    = None
        fragment_id_num = None

        for cr_key in cr_key_list:
            ### debug
            debug("name_service: chain_id / res_name keys")
            debug("  cr_key: chain_id='%s' res_name='%s'" % (
                cr_key[0],cr_key[1]))
            ### /debug

            ## get the next chain ID, use the cfr group's
            ## loaded chain_id if possible
            chain_id = next_chain_id(cr_key[0])

            ## if we are not out of chain IDs, use the new chain ID and
            ## reset the fragment_id
            if chain_id != None:
                new_chain_id    = chain_id
                fragment_id_num = 0

            elif new_chain_id == None or fragment_id_num == None:
                print "name_service: unable to assign any chain ids"
                sys.exit(1)

            ## get model dictionary
            model_dict = cr_dict[cr_key]

            ## inspect the model dictionary to determine the number
            ## of fragments in each model -- they should be the same
            ## and have a 1:1 cooraspondance; if not, match up the
            ## fragments as much as possible
            max_frags = -1
            for (model, frag_list) in model_dict.items():
                frag_list_len = len(frag_list)

                if max_frags == -1:
                    max_frags = frag_list_len
                    continue

                if max_frags != frag_list_len:
                    strx = "name_service: model fragments not identical"
                    debug(strx)
                    warning(strx)
                    max_frags = max(max_frags, frag_list_len)

            ## now iterate through the fragment lists in parallel and assign
            ## the new chain_id and fragment_id
            for i in range(max_frags):
                fragment_id_num += 1
                
                for frag_list in model_dict.values():
                    try:
                        frag = frag_list[i]
                    except IndexError:
                        continue

                    ## assign new chain_id and fragment_id, than place the
                    ## atom in the structure
                    for atm in frag:
                        atm.chain_id    = new_chain_id
                        atm.fragment_id = str(fragment_id_num)
                        self.struct.add_atom(atm, True)

            ## logging
            warning("NS: Added ChainID: %s with %3d Residues of Type: %s" % (
                new_chain_id, fragment_id_num, cr_key[1]))


    def read_atoms_finalize(self):
        """After loading all atom records, use the list of atom records to
        build the structure.
        """
        ## name atoms which didn't fit into the Structure hierarch with
        ## their names from the file
        self.name_service()

        ## sort structural objects into their correct order
        self.struct.sort()

    def read_metadata(self):
        """This method needs to be reimplemented in a fuctional subclass.
        The subclassed read_metadata method should call the various
        load_* methods to set non-atom coordinate data for the Structure.
        """
        pass

    def load_unit_cell(self, ucell_map):
        """Called by the implementation of load_metadata to load the
        unit cell pararameters for the structure.
        """
        for key in ("a", "b", "c", "alpha", "beta", "gamma"):
            if not ucell_map.has_key(key):
                debug("ucell_map missing: %s" % (key))
                return

        if ucell_map.has_key("space_group"):
            self.struct.unit_cell = UnitCell(
                a = ucell_map["a"],
                b = ucell_map["b"],
                c = ucell_map["c"],
                alpha = ucell_map["alpha"],
                beta = ucell_map["beta"],
                gamma = ucell_map["gamma"],
                space_group = ucell_map["space_group"])
        else:
            self.struct.unit_cell = UnitCell(
                a = ucell_map["a"],
                b = ucell_map["b"],
                c = ucell_map["c"],
                alpha = ucell_map["alpha"],
                beta = ucell_map["beta"],
                gamma = ucell_map["gamma"])

    def load_bonds(self, bond_map):
        """Call by the implementation of load_metadata to load bond
        information on the structure.  The keys of the bond map are a 2-tuple
        of the bonded Atom instances, and the value is a dictionary
        containing information on the type of bond, which may also
        be a symmetry operator.

        [bond_map]
        keys: (atm1, atm2)
        values: bond_data_map(s)

        [bond_data_map]
        bond_type -> text description of bond type: covalent, salt bridge,
                     hydrogen, cispeptide
                     
        atm1_symop -> symmetry operation (if any) to be applied to atm1
        atm2_symop -> same as above, for atom 2

        The symmetry operations themselves are a 3x4 array of floating point
        values composed of the 3x3 rotation matrix and the 3x1 translation.
        """

        ### XXX: fix this to build bonds in all models!!!
        
        for ((atm1, atm2), bd_map) in bond_map.items():

            ## check for files which, for some reason, define have a bond
            ## entry bonding the atom to itself
            if atm1 == atm2:
                warning("silly file defines self bonded atom")
                continue
            
            atm1.create_bonds(
                atom = atm2,
                bond_type = bd_map.get("bond_type"),
                atom1_symop = bd_map.get("atm1_symop"),
                atom2_symop = bd_map.get("atm2_symop"),
                standard_res_bond = False)

    def load_sequence(self, sequence_map):
        """The sequence map contains the following keys: chain_id: the
        chain ID fo the sequence; num_res: the number of residues in the
        sequence; sequence_list: a list of 3-letter codes of the residues
        in the sequence.
        """
        try:
            chain_id = sequence_map["chain_id"]
            sequence_list = sequence_map["sequence_list"]
        except KeyError:
            return

        ## add a copy of the sequence to each equivalent chain in
        ## all models of the structure
        for model in self.struct.iter_models():
            chain = model.get_chain(chain_id)
            if chain != None:
                chain.sequence = Sequence(library = self.struct.library,
                                          sequence_list = sequence_list[:])

    def load_alpha_helicies(self, helix_list):
        """The argument helix_list is a list of Python dictionaries with
        information to build build AlphaHelix objects into the Structure.

        The dictionary has attributes:
            helix_id:    The ID of the helix
            chain_id:    The chain_id where the helix is located
            frag_id1:    The start fragment_id of the helix
            frag_id2:    The end fragment_id of the helix
            helix_class: The PDB helix class number
            detaisl:     Text commont about the helix
        """
        for helix in helix_list:
            ## get required information or blow off the helix
            try:
                helix["helix_id"]
                helix["chain_id1"]
                helix["frag_id1"]
                helix["chain_id2"]
                helix["frag_id2"]
            except KeyError:
                continue

            ## build a AlphaHelix for every Model in the Structure
            for model in self.struct.iter_models():
                alpha_helix = AlphaHelix(model_id=model.model_id, **helix)
                model.add_alpha_helix(alpha_helix)
                alpha_helix.generate_segment()

    def load_beta_sheets(self, beta_sheet_list):
        """The argument beta_sheet_list is a list of Python dictionaries with
        information to build build BetaSheet objects into the Structure.

        The dictionary has attributes:
            sheet_id:    ID of the sheet
            num_strands: total number of strands in the beta sheet
            strand_list: list of dictionaries describing the strand with
                         the following attributes:

                chain_id1/frag_id1: chain_id and fragment_id of inital residue
                                    in the strand
                chain_id2/frag_id2: chain_id and fragment_id of end residue
                                    in the strand
                sense:              the sense of the strand with respect to the
                                    previous strand, either the string
                                    parallel or anti_parallel

                reg_chain_id, reg_frag_id, reg_atom:
                                    registration atom in current strand
                reg_prev_chain_id, reg_prev_frag_id, reg_prev_atom:
                                    registration atom in previous strand
        """
        for sheet in beta_sheet_list:
            ## get required info
            try:
                sheet["sheet_id"]
                sheet["strand_list"]
            except KeyError:
                continue

            ## iterate over all Models and add the BetaSheet description to
            ## each Model
            for model in self.struct.iter_models():
                beta_sheet = BetaSheet(model=model.model_id, **sheet)
        
                for strand in sheet["strand_list"]:
                    ## required strand info
                    try:
                        strand["chain_id1"]
                        strand["frag_id1"]
                        strand["frag_id1"]
                        strand["frag_id2"]
                    except KeyError:
                        continue

                    beta_strand = Strand(**strand)
                    beta_sheet.add_strand(beta_strand)

                model.add_beta_sheet(beta_sheet)
                beta_sheet.generate_segments()

    def load_sites(self, site_list):
        """The argument site_list is a list of Python dictionaries with
        information to build build Site objects into the Structure.
        """
        for site in site_list:
            ## check for required site info
            try:
                site["site_id"]
                site["fragment_list"]
            except KeyError:
                continue

            for model in self.struct.iter_models():
                site = Site(**site)
                model.add_site(site)
                site.generate_fragments()
        
    def read_metadata_finalize(self):
        """Called after the the metadata loading is complete.
        """
        pass
    
    def read_end(self):
        """This method needs to be reimplemented in a fuctional subclass.
        The subclassed read_end method can be used for any clean up from
        the file loading process you need, or may be left unimplemented.
        """
        pass

    def read_end_finalize(self):
        """Called for final cleanup after structure source readinging is
        done.  Currently, this method does nothing but may be used in
        future versions.
        """
        ## calculate sequences for all chains
        if "calc_sequence" in self.build_properties:
            for chain in self.struct.iter_chains():
                chain.calc_sequence()

        ## build bonds within structure
        if not "no_bonds" in self.build_properties:
            self.struct.add_bonds_from_library()


