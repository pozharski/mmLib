#!/usr/bin/env python
## Copyright 2002 by PyMMLib Development Group (see AUTHORS file)
## This code is part of the PyMMLib distrobution and governed by
## its license.  Please see the LICENSE file that should have been
## included as part of this package.

import math

import pygtk
pygtk.require("2.0")

import gobject
import gtk
import gtk.gtkgl

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

from mmLib.PDB            import PDBFile
from mmLib.Structure      import *
from mmLib.FileLoader     import LoadStructure, SaveStructure
from mmLib.GLViewer       import *
from mmLib.Extensions.TLS import *

try:
    ## try double-bufferedq
    glconfig = gtk.gdkgl.Config(
        mode = gtk.gdkgl.MODE_RGB|
        gtk.gdkgl.MODE_DOUBLE|
        gtk.gdkgl.MODE_DEPTH)

except gtk.gdkgl.NoMatches:
    ## try single-buffered
    glconfig = gtk.gdkgl.Config(
        mode = gtk.gdkgl.MODE_RGB|
        gtk.gdkgl.MODE_DEPTH)




###############################################################################
### TLS Search Algorithm
###

def print_U(tensor):
    print "%7.4f %7.4f %7.4f\n"\
          "%7.4f %7.4f %7.4f\n"\
          "%7.4f %7.4f %7.4f" % (
        tensor[0,0], tensor[0,1], tensor[0,2],
        tensor[1,0], tensor[1,1], tensor[1,2],
        tensor[2,0], tensor[2,1], tensor[2,2])


def iter_segments(chain, seg_len):
    """
    """
    segment = []
    for res in chain.iter_amino_acids():
        segment.append(res)

        if len(segment)<seg_len:
            continue
        
        if len(segment)>seg_len:
            segment = segment[1:]

        atom_list = AtomList()
        for rx in segment:
            for atm in rx.iter_atoms():
                atom_list.append(atm)

        yield atom_list


def fit_TLS_segments(struct, seg_width = 6):
    print """\
    ## Calculating TLS parameters for a single rigid body group composed of
    ## all the amino acids
    """
    print "## <group num> <num atoms> <Badv> <R> <dP2>"

    ## list of all TLS groups
    tls_list    = []
    segments    = []
    cur_segment = []

    for chain in struct.iter_chains():
        for seg_atom_list in iter_segments(chain, seg_width):

            atm0 = seg_atom_list[0]
            atmX = seg_atom_list[-1]
            name = "%s-%s" % (atm0.fragment_id, atmX.fragment_id)

            ## new tls group for segment
            tls = TLSGroup()
            tls.name = name

            ## add all atoms to the TLS group which are at full occupancy
            for atm in seg_atom_list:
                if atm.occupancy<1.0:
                    continue
                tls.append(atm)

            if len(tls)==0:
                continue

            ## set the origin of the TLS group to the centroid, and also
            ## save it under calc_origin because origin will be overwritten
            ## using the COR after the least squares fit
            tls.origin      = tls.calc_centroid()
            tls.calc_origin = tls.origin

            ## calculate tensors and print
            tls.calc_TLS_least_squares_fit()
            calc = tls.calc_COR()

            if min(eigenvalues(tls.L))<=0.0:
                   print "%s: removed negitive L eigenvalue" % (tls.name)     
                   continue
            elif min(eigenvalues(tls.T))<=0.0:
                   print "%s: removed negitive T eigenvalue" % (tls.name)
                   continue
            elif  min(eigenvalues(calc["rT'"]))<=0.0:
                print "%s: removed negitive rT' eigenvalue" % (tls.name)
                continue

            tls_list.append(tls)

            ### <verify> the independance of the original origin of calculation
            tls_check = TLSGroup(tls)
            tls_check.origin = tls.origin.copy() + \
                               array([random.random()*10.0,
                                      random.random()*10.0,
                                      random.random()*10.0])

            tls_check.calc_TLS_least_squares_fit()
            calc_check = tls_check.calc_COR()

            assert len(tls)==len(tls_check)

            for i in range(len(tls)):
                atmi  = tls[i]
                atmci = tls_check[i]

                assert atmi==atmci
                assert allclose(atmi.position,atmci.position)
                assert allclose(atmi.get_U(),atmci.get_U())

                U = tls.calc_Utls(tls.T,
                                  tls.L,
                                  tls.S,
                                  atmi.position - tls.origin)

                Ucheck = tls_check.calc_Utls(tls_check.T,
                                             tls_check.L,
                                             tls_check.S,
                                             atmci.position - tls_check.origin)
                
                try:
                    assert allclose(U, Ucheck, 1.0e-4)
                except AssertionError:
                    print atm
                    print_U(U)
                    print_U(Ucheck)
                    raise

            try:
                assert allclose(calc["COR"], calc_check["COR"], 1.0e-4)
            except AssertionError:
                print "COR:       ", calc["COR"]
                print "COR_CHECK: ", calc_check["COR"]
                raise
            
            assert allclose(calc["T'"],  calc_check["T'"],  1.0e-4)
            assert allclose(calc["L'"],  calc_check["L'"],  1.0e-4)
            assert allclose(calc["S'"],  calc_check["S'"],  1.0e-4)
            ### </verify>


            ## calculate matching statistics
            calcs = tls.shift_COR()
            
            Rfact   = tls.calc_R()
            dP2     = tls.calc_adv_DP2uij()
            dP2n    = tls.calc_adv_normalized_DP2uij()
            Suij    = tls.calc_adv_Suij()
            tls.fit = dP2

            ## calculate the average Biso value of the TLS group
            Uadv = 0.0
            for atm in tls:
                Uadv += trace(atm.get_U())/3.0
            Uadv = Uadv / float(len(tls))

            ## print out statistics
            print str(name).ljust(8),

            print str(tls_list.index(tls)).ljust(5),

            x = "%d" % (len(tls))
            print x.ljust(8),

            x = "%.3f" % (Uadv * 8*math.pi**2)
            print x.ljust(10),

            x = "%.3f" % (Rfact)
            print x.ljust(8),

            x = "%.4f" % (dP2)
            print x.ljust(10),

            x = "%.4f" % (dP2n)
            print x.ljust(10),

            x = "%.4f" % (Suij)
            print x.ljust(10),
            
            x = "%.2f" % (max(eigenvalues(tls.L))*rad2deg2)
            print x.ljust(7),

            if (max(eigenvalues(tls.L))*rad2deg2)<0.0:
                tls_list.remove(tls)
                print "removed small libration",
            elif dP2>0.1:
                tls_list.remove(tls)
                print "removed bad match",
                cur_segment = []
            else:
                if len(cur_segment)==0:
                    segments.append(cur_segment)
                cur_segment.append(tls)

            print

    ## now just grab the best segment from the group
    ret_list = []

    for seg in segments:
        for i in range(len(seg)):
            tls = tls_list[i]

            try:
                prev = tls_list[i-1]
            except IndexError:
                prev = None

            try:
                next = tls_list[i+1]
            except IndexError:
                next = None

            if prev==None:
                if next.fit>tls.fit:
                    ret_list.append(tls)
            elif next==None:
                if prev.fit>tls.fit:
                    ret_list.append(tls)

            elif prev.fit>tls.fit and next.fit>tls.fit:
                ret_list.append(tls)


    return tls_list

###############################################################################
    

###############################################################################
### GTK OpenGL Viewer Widget Using GtkGlExt/PyGtkGLExt
###
### see http://gtkglext.sourceforge.net/ for information on GtkGLExt and
### OpenGL binding in GTK 2.0
###

class GtkGLViewer(gtk.gtkgl.DrawingArea, GLViewer):
    def __init__(self):
        gtk.gtkgl.DrawingArea.__init__(self)
        GLViewer.__init__(self)
        gtk.gtkgl.widget_set_gl_capability(self, glconfig)
        
        self.set_size_request(300, 300)

        self.connect('button_press_event',  self.button_press_event)
        self.connect('motion_notify_event', self.motion_notify_event)
        self.connect('realize',             self.realize)
        self.connect('map',                 self.map)
        self.connect('unmap',               self.unmap)
        self.connect('configure_event',     self.configure_event)
        self.connect('expose_event',        self.expose_event)
        self.connect('destroy',             self.destroy)

    def gl_begin(self):
        """Sets up the OpenGL drawing context for drawing.  If
        no context is availible (hiddent window, not created yet),
        this method returns False, otherwise it returns True.
        """
        gl_drawable = gtk.gtkgl.DrawingArea.get_gl_drawable(self)
        gl_context  = gtk.gtkgl.DrawingArea.get_gl_context(self)
        if gl_drawable==None or gl_context==None:
            return False
        
	if not gl_drawable.gl_begin(gl_context):
            return False

        return True

    def gl_end(self):
        """Ends a sequence of OpenGL drawing calls, then swaps drawing
        buffers.
        """
        gl_drawable = gtk.gtkgl.DrawingArea.get_gl_drawable(self)
	if gl_drawable.is_double_buffered():
            gl_drawable.swap_buffers()
	else:
            glFlush()
        
        gl_drawable.gl_end()

    def map(self, glarea):
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK   |
                        gtk.gdk.BUTTON_RELEASE_MASK |
                        gtk.gdk.BUTTON_MOTION_MASK  |
                        gtk.gdk.POINTER_MOTION_MASK)
        return gtk.TRUE

    def unmap(self, glarea):
        return gtk.TRUE

    def realize(self, glarea):
        if self.gl_begin()==True:
            self.glv_init()
            self.gl_end()
        return gtk.TRUE

    def configure_event(self, glarea, event):
        x, y, width, height = glarea.get_allocation()

        if self.gl_begin()==True:
            self.glv_resize(width, height)
            self.gl_end()

        self.queue_draw()
        return gtk.TRUE

    def expose_event(self, glarea, event):
        if self.gl_begin()==True:
            self.glv_render()
            self.gl_end()
        return gtk.TRUE

    def button_press_event(self, glarea, event):
        self.beginx = event.x
        self.beginy = event.y

    def motion_notify_event(self, glarea, event):
        width     = glarea.allocation.width
        height    = glarea.allocation.height

        x = 0.0
        y = 0.0
        z = 0.0

        rotx = 0.0
        roty = 0.0
        rotz = 0.0
        
        if (event.state & gtk.gdk.BUTTON1_MASK):
            roty += 360.0 * ((event.x - self.beginx) / float(width)) 
            rotx += 360.0 * ((event.y - self.beginy) / float(height))

        elif (event.state & gtk.gdk.BUTTON2_MASK):
            z = 50.0 * ((event.y - self.beginy) / float(height))
            rotz += 360.0 * ((event.x - self.beginx) / float(width)) 

        elif (event.state & gtk.gdk.BUTTON3_MASK):
            x = 50.0 * ((event.x - self.beginx) / float(height))
            y = 50.0 * (-(event.y - self.beginy) / float(height))

        self.glv_translate(x, y, z)
        self.glv_rotate(rotx, roty, rotz)

        self.beginx = event.x
        self.beginy = event.y

        self.queue_draw()

    def destroy(self, glarea):
        ## XXX: delete all opengl draw lists
        return gtk.TRUE

    def glv_redraw(self):
        self.queue_draw()


class StructDetailsDialog(gtk.Dialog):
    def __init__(self, context):
        self.context = context
        
        gtk.Dialog.__init__(self,
                            "Selection Information",
                            self.context.window,
                            gtk.DIALOG_DESTROY_WITH_PARENT)

        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.set_default_size(400, 400)
        
        self.connect("destroy", self.response_cb)
        self.connect("response", self.response_cb)

        ## make the print box
        sw = gtk.ScrolledWindow()
        self.vbox.add(sw)
        sw.set_border_width(5)
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)


        self.store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
     
        treeview = gtk.TreeView(self.store)
        sw.add(treeview)
        treeview.set_rules_hint(gtk.TRUE)
        treeview.set_search_column(0)

        column = gtk.TreeViewColumn(
            "mmLib.Structure Method",
            gtk.CellRendererText(),
            text=0)
        treeview.append_column(column)
    
        column = gtk.TreeViewColumn(
            "Return Value",
            gtk.CellRendererText(),
            text=1)
        treeview.append_column(column)

        self.show_all()

    def response_cb(self, *args):
        self.destroy()
    
    def add_line(self, key, value):
        iter = self.store.append()
        self.store.set(iter, 0, key, 1, str(value))

    def set_struct_obj(self, struct_obj):
        self.store.clear()

        if isinstance(struct_obj, Residue):
            self.add_line("Residue.res_name", struct_obj.res_name)
            self.add_line("Residue.get_offset_residue(-1)",
                          struct_obj.get_offset_residue(-1))
            self.add_line("Residue.get_offset_residue(1)",
                          struct_obj.get_offset_residue(1))

        if isinstance(struct_obj, Fragment):
            bonds = ""
            for bond in struct_obj.iter_bonds():
                bonds += str(bond)
            self.add_line("Fragment.iter_bonds()", bonds)

        if isinstance(struct_obj, AminoAcidResidue):
            self.add_line("AminoAcidResidue.calc_mainchain_bond_length()",
                          struct_obj.calc_mainchain_bond_length())
            self.add_line("AminoAcidResidue.calc_mainchain_bond_angle()",
                          struct_obj.calc_mainchain_bond_angle())
            self.add_line("AminoAcidResidue.calc_torsion_psi()",
                          struct_obj.calc_torsion_psi())
            self.add_line("AminoAcidResidue.calc_torsion_phi()",
                          struct_obj.calc_torsion_phi())
            self.add_line("AminoAcidResidue.calc_torsion_omega()",
                          struct_obj.calc_torsion_omega())
            self.add_line("AminoAcidResidue.calc_torsion_chi()",
                          struct_obj.calc_torsion_chi())

        if isinstance(struct_obj, Atom):
            self.add_line("Atom.element", struct_obj.element)
            self.add_line("Atom.name", struct_obj.name)
            self.add_line("Atom.occupancy", struct_obj.occupancy)
            self.add_line("Atom.temp_factor", struct_obj.temp_factor)
            self.add_line("Atom.U", struct_obj.U)
            self.add_line("Atom.position", struct_obj.position)
            self.add_line("len(Atom.bond_list)", len(struct_obj.bond_list))
            self.add_line("Atom.calc_anisotropy()",
                          struct_obj.calc_anisotropy())




###############################################################################
### GLProperty Browser Components for browsing and changing GLViewer.GLObject
### properties
###


def markup_vector3(vector):
    return "<small>%7.4f %7.4f %7.4f</small>" % (
        vector[0], vector[1], vector[2])

def markup_matrix3(tensor):
    """Uses pango markup to make the presentation of the tenosr
    look nice.
    """
    return "<small>%7.4f %7.4f %7.4f\n"\
                  "%7.4f %7.4f %7.4f\n"\
                  "%7.4f %7.4f %7.4f</small>" % (
               tensor[0,0], tensor[0,1], tensor[0,2],
               tensor[1,0], tensor[1,1], tensor[1,2],
               tensor[2,0], tensor[2,1], tensor[2,2])


class ColorSelection(gtk.Combo):
    def __init__(self):
        gtk.Combo.__init__(self)

        self.color = None

        self.color_dict = {
            "white":   (1.0, 1.0, 1.0),
            "red":     (1.0, 0.0, 0.0),
            "green":   (0.0, 1.0, 0.0),
            "blue":    (0.0, 0.0, 1.0) }
        
        self.set_popdown_strings(
            ["Random",
             "Color By Atom",
             "White",
             "Red",
             "Green",
             "Blue" ])

        self.entry.connect("activate", self.activate, None)

    def activate(self, entry, junk):
        txt = self.entry.get_text()

        ## color format: r, g, b
        try:
            r, g, b = txt.split(",")
            color = (float(r), float(g), float(b))
        except ValueError:
            pass
        else:
            self.set_color(color)
            return

        ## color format: Random
        if txt=="Random":
            color = (random.random(),
                     random.random(),
                     random.random())
            self.set_color(color)
            return

        ## color format: keywords
        if txt=="Color By Atom":
            self.set_color(None)
            return

        ## color fomat: match color name
        try:
            color = self.color_dict[txt.lower()]
        except KeyError:
            pass
        else:
            self.set_color(color)
            return

    def match_color_name(self, color):
        if color==None:
            return "Color By Atom"

        for color_name, color_val in self.color_dict.items():
            if color==color_val:
                return color_name

        return "%3.2f,%3.2f,%3.2f" % (color[0], color[1], color[2])
    
    def set_color(self, color):
        self.color = color
        name       = self.match_color_name(color)
        self.entry.set_text(name)

    def get_color(self):
        self.activate(self.entry, None)
        return self.color


class GLPropertyEditor(gtk.Notebook):
    """Gtk Widget which generates a customized editing widget for a
    GLObject widget supporting GLProperties.
    """
    def __init__(self, gl_object):
        gtk.Notebook.__init__(self)
        self.set_scrollable(gtk.TRUE)
        self.connect("destroy", self.destroy)

        self.gl_object = gl_object
        self.gl_object.glo_add_update_callback(self.properties_update_cb)

        ## property name -> widget dictionary
        self.prop_widget_dict = {}

        ## count the number of properties/pages to be displayed
        page_prop_dict = {}
        num_props = 0
        for prop_desc in self.gl_object.glo_iter_property_desc():
            if prop_desc.get("hidden", False)==True:
                continue

            catagory = prop_desc.get("catagory", "Show/Hide")
            try:
                page_prop_dict[catagory].append(prop_desc)
            except KeyError:
                page_prop_dict[catagory] = [prop_desc]

        ## sort pages
        catagories = page_prop_dict.keys()
        if "Show/Hide" in catagories:
            catagories.remove("Show/Hide")
            catagories.insert(0, "Show/Hide")
            
        ## add Notebook pages and tables
        table_dict = {}
        for catagory in catagories:
            prop_list = page_prop_dict[catagory]

            num_props = len(prop_list)

            table = gtk.Table(2, num_props, gtk.FALSE)
            self.append_page(table, gtk.Label(catagory))

            table.set_border_width(5)
            table.set_row_spacings(5)
            table.set_col_spacings(10)

            table_row = 0

            size_group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)

            ## boolean types first since the toggle widgets don't look good mixed
            ## with the entry widgets
            for prop in prop_list:
                ## only handling boolean right now
                if prop["type"]!="boolean":
                    continue

                edit_widget = self.new_property_edit_widget(prop)
                self.prop_widget_dict[prop["name"]] = edit_widget 

                align = gtk.Alignment(0.0, 0.5, 0.0, 0.0)
                align.add(edit_widget)

                table.attach(align, 0, 2, table_row, table_row+1, gtk.FILL|gtk.SHRINK, 0, 0, 0)
                table_row += 1

            ## create and layout the editing widgets
            for prop in prop_list:
                ## boolean types were already handled
                if prop["type"]=="boolean":
                    continue

                label_widget = self.new_property_label_widget(prop)
                #table.attach(label_widget, 0, 1, table_row,table_row+1, gtk.EXPAND|gtk.FILL, 0, 0, 0)
                table.attach(label_widget, 0, 1, table_row,table_row+1, gtk.FILL|gtk.SHRINK, 0, 0, 0)

                edit_widget = self.new_property_edit_widget(prop)
                self.prop_widget_dict[prop["name"]] = edit_widget 

                size_group.add_widget(edit_widget)
                table.attach(edit_widget, 1, 2, table_row, table_row+1, gtk.FILL|gtk.SHRINK, 0, 0, 0)
                table_row += 1

        self.properties_update_cb(self.gl_object.properties)

    def destroy(self, widget):
        """Called after this widget is destroyed.  Make sure to remove the callback we installed
        to monitor property changes.
        """
        self.gl_object.glo_remove_update_callback(self.properties_update_cb)

    def new_property_label_widget(self, prop):
        """Returns the label widget for property editing.
        """
        label = gtk.Label(prop.get("desc", prop["name"]))
        label.set_alignment(0, 1)
        return label

    def new_property_edit_widget(self, prop):
        """Returns the editing widget for a property.
        """
        if prop["type"]=="boolean":
            widget = gtk.CheckButton(prop.get("desc", prop["name"]))
        elif prop["type"]=="integer":
            widget = gtk.Entry()
        elif prop["type"]=="float":
            widget = gtk.Entry()
        elif prop["type"]=="array(3)":
            widget = gtk.Label()
            widget.set_markup(markup_vector3(self.gl_object.properties[prop["name"]]))
        elif prop["type"]=="array(3,3)":
            widget = gtk.Label()
            widget.set_markup(markup_matrix3(self.gl_object.properties[prop["name"]]))
        elif prop["type"]=="color":
            widget = ColorSelection()
        else:
            text = str(self.gl_object.properties[prop["name"]])
            widget = gtk.Label(text)

        return widget

    def properties_update_cb(self, updates={}, actions=[]):
        """Read the property values and update the widgets to display the values.
        """
        for name in updates:
            try:
                widget = self.prop_widget_dict[name]
            except KeyError:
                continue

            prop_desc = self.gl_object.glo_get_property_desc(name)
            
            if prop_desc["type"]=="boolean":
                if self.gl_object.properties[name]==True:
                    widget.set_active(gtk.TRUE)
                else:
                    widget.set_active(gtk.FALSE)
            elif prop_desc["type"]=="integer":
                text = str(self.gl_object.properties[name])
                widget.set_text(text)
            elif prop_desc["type"]=="float":
                text = str(self.gl_object.properties[name])
                widget.set_text(text)
            elif prop_desc["type"]=="array(3)":
                widget.set_markup(markup_vector3(self.gl_object.properties[name]))
            elif prop_desc["type"]=="array(3,3)":
                widget.set_markup(markup_matrix3(self.gl_object.properties[name]))
            elif prop_desc["type"]=="color":
                widget.set_color(self.gl_object.properties[name])
            else:
                widget.set_text(str(self.gl_object.properties[name]))

    def update(self):
        """Read values from widgets and apply them to the gl_object
        properties.
        """
        update_dict = {}
        
        for prop in self.gl_object.glo_iter_property_desc():
            name = prop["name"]

            try:
                widget = self.prop_widget_dict[name]
            except KeyError:
                continue

            if prop["type"]=="boolean":
                if widget.get_active()==gtk.TRUE:
                    update_dict[name] = True
                else:
                    update_dict[name] = False

            elif prop["type"]=="integer":
                try:
                    value = int(widget.get_text())
                except ValueError:
                    pass
                else:
                    update_dict[name] = value
                    
            elif prop["type"]=="float":
                try:
                    value = float(widget.get_text())
                except ValueError:
                    pass
                else:
                    update_dict[name] = value

            elif prop["type"]=="color":
                update_dict[name] = widget.get_color()

        self.gl_object.glo_update_properties(**update_dict)


class GLPropertyTreeControl(gtk.TreeView):
    """Hierarchical tree view of the GLObjects which make up
    the molecular viewer.  The purpose of this widget is to alllow
    easy navigation through the hierarchy.
    """
    
    def __init__(self, gl_object_root, glo_select_cb):
        self.gl_object_root = gl_object_root
        self.glo_select_cb  = glo_select_cb
        self.path_glo_dict  = {}
        
        gtk.TreeView.__init__(self)
        self.get_selection().set_mode(gtk.SELECTION_BROWSE)
        
        self.connect("row-activated", self.row_activated_cb)
        self.connect("button-release-event", self.button_release_event_cb)

        self.model = gtk.TreeStore(gobject.TYPE_STRING)
        self.set_model(self.model)

        cell = gtk.CellRendererText()
        self.column = gtk.TreeViewColumn("OpenGL Renderer", cell)
        self.column.add_attribute(cell, "text", 0)
        self.append_column(self.column)

        self.rebuild_gl_object_tree()

    def row_activated_cb(self, tree_view, path, column):
        """Retrieve selected node, then call the correct set method for the
        type.
        """
        glo = self.get_gl_object(path)
        self.glo_select_cb(glo)

    def button_release_event_cb(self, tree_view, bevent):
        """
        """
        x = int(bevent.x)
        y = int(bevent.y)

        try:
            (path, col, x, y) = self.get_path_at_pos(x, y)
        except TypeError:
            return gtk.FALSE

        self.row_activated(path, self.column)
        return gtk.FALSE

    def get_gl_object(self, path):
        """Return the GLObject from the treeview path.
        """
        glo = self.path_glo_dict[path]
        return glo

    def rebuild_gl_object_tree(self):
        """Clear and refresh the view of the widget according to the
        self.struct_list
        """

        ## first get a refernence to the current selection
        ## so it can be restored after the reset if it hasn't
        ## been removed
        model, iter = self.get_selection().get_selected()
        if iter!=None:
            selected_glo = self.path_glo_dict[model.get_path(iter)]
        else:
            selected_glo = None

        ## now record how the tree is expanded so the expansion
        ## can be restored after rebuilding
        expansion_dict = {}
        for path, glo in self.path_glo_dict.items():
            expansion_dict[glo] = self.row_expanded(path)

        ## rebuild the tree view using recursion
        self.path_glo_dict = {}
        self.model.clear()
        
        def redraw_recurse(glo, parent_iter):
            iter = self.model.append(parent_iter)
            path = self.model.get_path(iter)

            self.path_glo_dict[path] = glo
            
            self.model.set(iter, 0, glo.glo_name())

            for child in glo.glo_iter_children():
                redraw_recurse(child, iter)
    
        redraw_recurse(self.gl_object_root, None)

        ## restore expansions and selections
        for path, glo in self.path_glo_dict.items():
            try:
                expanded = expansion_dict[glo]
            except KeyError:
                continue
            if expanded==gtk.TRUE:
                for i in range(1, len(path)):
                    self.expand_row(path[:i], gtk.FALSE)

        if selected_glo!=None:
            self.select_gl_object(selected_glo)

    def select_gl_object(self, target_glo):
        """Selects a gl_object which must be a glo_root or a
        decendant of glo_root.
        """
        ## try to find and select target_glo
        for path, glo in self.path_glo_dict.items():
            if id(glo)==id(target_glo):

                for i in range(1, len(path)):
                    self.expand_row(path[:i], gtk.FALSE)

                self.get_selection().select_path(path)
                self.glo_select_cb(glo)
                return

        ## unable to find target_glo, select the root
        self.select_gl_object(self.gl_object_root)
        self.glo_select_cb(self.gl_object_root)


class GLPropertyEditDialog(gtk.Dialog):
    """Open a dialog for editing a single GLObject properties.
    """

    def __init__(self, parent_window, gl_object):
        title = "Edit GLProperties: %s" % (gl_object.glo_name())

        gtk.Dialog.__init__(
            self,
            title,
            parent_window,
            gtk.DIALOG_DESTROY_WITH_PARENT)

        self.set_resizable(gtk.FALSE)
        self.connect("response", self.response_cb)

        self.gl_prop_editor = GLPropertyEditor(gl_object)
        self.vbox.pack_start(self.gl_prop_editor, gtk.TRUE, gtk.TRUE, 0)

        self.add_button(gtk.STOCK_APPLY, 100)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        self.show_all()

    def response_cb(self, dialog, response_code):
        if response_code==gtk.RESPONSE_CLOSE:
            self.destroy()
        if response_code==100:
            self.gl_prop_editor.update()
    

class GLPropertyBrowserDialog(gtk.Dialog):
    """
    """
    def __init__(self, parent_window, glo_root):
        gl_object_root = glo_root
        title = "Browse OpenGL Properties: %s" % (gl_object_root.glo_name())

        gtk.Dialog.__init__(
            self,
            title,
            parent_window,
            gtk.DIALOG_DESTROY_WITH_PARENT)

        self.connect("response", self.response_cb)
        self.add_button(gtk.STOCK_APPLY, 100)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        ## widgets
        self.hpaned = gtk.HPaned()
        self.vbox.pack_start(self.hpaned, gtk.TRUE, gtk.TRUE, 0)
        self.hpaned.set_border_width(2)

        ## property tree control
        self.sw1 = gtk.ScrolledWindow()
        self.hpaned.add1(self.sw1)
        
        self.gl_tree_ctrl = GLPropertyTreeControl(
            gl_object_root,
            self.gl_tree_ctrl_selected)

        self.sw1.add(self.gl_tree_ctrl)

        ## always start with the root selected
        self.gl_prop_editor = None
        self.select_gl_object(gl_object_root)

        self.show_all()

    def response_cb(self, dialog, response_code):
        if response_code==gtk.RESPONSE_CLOSE:
            self.destroy()
        if response_code==100:
            self.gl_prop_editor.update()    

    def rebuild_gl_object_tree(self):
        """Rebuilds the GLObject tree view.
        """
        self.gl_tree_ctrl.rebuild_gl_object_tree()

    def gl_tree_ctrl_selected(self, glo):
        """Callback invoked by the GLPropertyTreeControl when a
        GLObject is selected
        """
        ## remove the current property editor if there is one
        if self.gl_prop_editor!=None:
            if self.gl_prop_editor.gl_object==glo:
                return

            self.hpaned.remove(self.gl_prop_editor)
            self.gl_prop_editor = None

        ## create new property editor
        self.gl_prop_editor = GLPropertyEditor(glo)
        self.hpaned.add2(self.gl_prop_editor)
        self.gl_prop_editor.show_all()

    def select_gl_object(self, glo):
        """Selects the given GLObject for editing by
        simulating a selection through the GLPropertyTreeControl.
        """
        self.gl_tree_ctrl.select_gl_object(glo)


###############################################################################
### TLS Analysis Dialog 
###


class TLSDialog(gtk.Dialog):
    """Dialog for the visualization and analysis of TLS model parameters
    describing rigid body motion of a structure.  The TLS model parameters
    can either be extracted from PDB REMARK statements, or loaded from a
    CCP4/REFMAC TLSIN file.
    """    

    def __init__(self, **args):
        self.main_window    = args["main_window"]
        self.struct_context = args["struct_context"]
        self.sel_tls_group  = None

        self.animation_time = 0.0
        self.animation_list = []
        self.tls_group_list = []

        gtk.Dialog.__init__(
            self,
            "TLS Analysis: %s" % (str(self.struct_context.struct)),
            self.main_window.window,
            gtk.DIALOG_DESTROY_WITH_PARENT)

        self.add_button("Open TLSIN", 100)
        self.add_button("Graphics Properties", 101)
        self.add_button("Fit TLS Groups", 102)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

        self.set_default_size(400, 400)
        
        self.connect("destroy", self.destroy_cb)
        self.connect("response", self.response_cb)

        ## make the print box
        sw = gtk.ScrolledWindow()
        self.vbox.add(sw)
        sw.set_border_width(5)
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        self.model = gtk.TreeStore(
            gobject.TYPE_BOOLEAN,   #0
            gobject.TYPE_BOOLEAN,   #1
            gobject.TYPE_STRING,    #2
            gobject.TYPE_STRING,    #3
            gobject.TYPE_STRING,    #4
            gobject.TYPE_STRING)    #5
     
        treeview = gtk.TreeView(self.model)
        sw.add(treeview)
        treeview.connect("row-activated", self.row_activated_cb)
        treeview.set_rules_hint(gtk.TRUE)

        cell_rend = gtk.CellRendererToggle()
        column = gtk.TreeViewColumn("Show", cell_rend)
        column.add_attribute(cell_rend, "active", 0)
        treeview.append_column(column)
        cell_rend.connect("toggled", self.view_toggled)

        cell_rend = gtk.CellRendererToggle()
        column = gtk.TreeViewColumn("Animate", cell_rend)
        column.add_attribute(cell_rend, "active", 1)
        treeview.append_column(column)
        cell_rend.connect("toggled", self.animate_toggled)

        cell_rend = gtk.CellRendererText()
        column = gtk.TreeViewColumn("TLS Group", cell_rend)
        column.add_attribute(cell_rend, "markup", 2)
        treeview.append_column(column)

        cell_rend = gtk.CellRendererText()
        column = gtk.TreeViewColumn("T(A^2)", cell_rend)
        column.add_attribute(cell_rend, "markup", 3)
        treeview.append_column(column)

        cell_rend = gtk.CellRendererText()
        column = gtk.TreeViewColumn("L(deg^2)", cell_rend)
        column.add_attribute(cell_rend, "markup", 4)
        treeview.append_column(column)

        cell_rend = gtk.CellRendererText()
        column = gtk.TreeViewColumn("S(A*deg)", cell_rend)
        column.add_attribute(cell_rend, "markup", 5)
        treeview.append_column(column)

        self.show_all()

        gobject.timeout_add(200, self.timeout_cb)

        self.load_PDB(self.struct_context.struct.path)

    def response_cb(self, dialog, response_code):
        """Responses to dialog events.
        """
        if response_code==gtk.RESPONSE_CLOSE:
            self.destroy()
            
        elif response_code==100:
            file_sel = gtk.FileSelection("Select TLSOUT File")
            file_sel.hide_fileop_buttons()
            response = file_sel.run()

            if response==gtk.RESPONSE_OK:
                path = file_sel.get_filename()
                if path!=None and path!="":
                    self.load_TLSOUT(path)
            file_sel.destroy()
            
        elif response_code==101 and self.sel_tls_group!=None:
            ## use the GLPropertyBrowserDialog associated with
            ## the application main window to present the
            ## properties of the gl_tls object for modification
            
            self.main_window.edit_properties_gl_object(
                self.sel_tls_group.gl_tls)

        elif response_code==102:
            self.load_TLS_fit()

    def destroy_cb(self, *args):
        """Destroy the TLS dialog and everything it has built
        in the GLObject viewer.
        """
        self.clear_tls_groups()

    def get_tls_group(self, path):
        return self.tls_group_list[int(path)]

    def row_activated_cb(self, tree_view, path, column):
        row = int(path[0])
        self.sel_tls_group = self.tls_group_list[row]

    def view_toggled(self, cell, path):
        """Visible/Hidden TLS representation.
        """
        ## why, oh why??
        path = int(path)

        # get toggled iter
        iter = self.model.get_iter((path,))

        show_vis = self.model.get_value(iter, 0)
        tls_group = self.tls_group_list[path]
    
        # do something with the value
        if show_vis==gtk.TRUE:
            tls_group.gl_tls.glo_update_properties(visible=False)
        else:
            tls_group.gl_tls.glo_update_properties(visible=True)

    def animate_toggled(self, cell, path):
        """Start/Stop TLS Animation.
        """
        path      = int(path)
        tls_group = self.tls_group_list[path]

        iter      = self.model.get_iter((path,))
        animate   = self.model.get_value(iter, 1)

        if animate==gtk.FALSE:
            self.model.set(iter, 1, gtk.TRUE)
            self.animation_list.append(tls_group)
        elif animate==gtk.TRUE:
            self.model.set(iter, 1, gtk.FALSE)
            self.animation_list.remove(tls_group)

    def add_tls_group(self, tls_group):
        """Adds the TLS group and creates tls.gl_tls OpenGL
        renderer.
        """
        self.tls_group_list.append(tls_group)
        
        tls_group.gl_tls = GLTLSGroup(tls_group=tls_group)
        self.struct_context.gl_struct.glo_add_child(tls_group.gl_tls)
        tls_group.gl_tls.glo_add_update_callback(self.update_cb)

        ## rebuild GUI viewers
        self.main_window.gl_prop_browser_rebuild_gl_object_tree()
        self.redraw_treeview()

    def clear_tls_groups(self):
        """Remove the current TLS groups, including destroying
        the tls.gl_tls OpenGL renderer
        """
        gl_viewer = self.main_window.struct_gui.gtkglviewer

        for tls_group in self.tls_group_list:
            gl_viewer.glv_remove_draw_list(tls_group.gl_tls)
            tls_group.gl_tls.glo_remove_update_callback(self.update_cb)
            del tls_group.gl_tls
        
        self.tls_group_list = []
        self.animation_list = []

        ## rebuild GUI viewers
        self.main_window.gl_prop_browser_rebuild_gl_object_tree()
        self.redraw_treeview()

    def update_cb(self, updates={}, actions=[]):
        """Property change callback from the GLTLSGroups.
        """
        i = 0
        for tls in self.tls_group_list:
            iter = self.model.get_iter((i,))

            if tls.gl_tls.properties["visible"]==True:
                self.model.set(iter, 0, gtk.TRUE)
            else:
                self.model.set(iter, 0, gtk.FALSE)

            i += 1

    def load_PDB(self, path):
        """Load TLS descriptions from PDB REMARK records.
        """
        self.clear_tls_groups()
        
        tls_file = TLSInfoList()
        pdb_file = PDBFile()
        pdb_file.load_file(path)
        pdb_file.record_processor(tls_file)

        for tls_info in tls_file:
            tls_group = tls_info.make_tls_group(self.struct_context.struct)
            tls_group.tls_info = tls_info
            self.add_tls_group(tls_group)
            
    def load_TLSOUT(self, path):
        """Load TLS descriptions from a REMAC/CCP4 TLSOUT file.
        """
        print "## loading = ",path
        
        self.clear_tls_groups()

        tls_file = TLSInfoList()
        tls_file.load_refmac_tlsout_file(open(path, "r"))
    
        for tls_info in tls_file:
            tls_group = tls_info.make_tls_group(self.struct_context.struct)
            tls_group.tls_info = tls_info
            self.add_tls_group(tls_group)

    def load_TLS_fit(self):
        """Fit TLS groups to sequence segments
        """
        self.clear_tls_groups()

        for tls_group in fit_TLS_segments(self.struct_context.struct):
            self.add_tls_group(tls_group)
        
    def markup_tls_name(self, tls_info):
        listx = []
        for (chain_id1, frag_id1, chain_id2, frag_id2, sel) in tls_info.range_list:
            listx.append("%s%s-%s%s %s" % (chain_id1, frag_id1, chain_id2, frag_id2, sel))
        return "<small>"+string.join(listx, "\n")+"</small>"

    def markup_tensor(self, tensor):
        """Uses pango markup to make the presentation of the tenosr
        look nice.
        """
        return "<small>%7.4f %7.4f %7.4f\n"\
                      "%7.4f %7.4f %7.4f\n"\
                      "%7.4f %7.4f %7.4f</small>" % (
                   tensor[0,0], tensor[0,1], tensor[0,2],
                   tensor[1,0], tensor[1,1], tensor[1,2],
                   tensor[2,0], tensor[2,1], tensor[2,2])
           
    def redraw_treeview(self):
        """Clear and redisplay the TLS group treeview list.
        """
        self.model.clear()

        for tls in self.tls_group_list:
            iter = self.model.append(None)

            if tls.gl_tls.properties["visible"]==True:
                self.model.set(iter, 0, gtk.TRUE)
            else:
                self.model.set(iter, 0, gtk.FALSE)

            if tls in self.animation_list:
                self.model.set(iter, 1, gtk.TRUE)
            else:
                self.model.set(iter, 1, gtk.FALSE)


            if hasattr(tls, "tls_info"):
                self.model.set(iter, 2, self.markup_tls_name(tls.tls_info))
            elif hasattr(tls, "name"):
                self.model.set(iter, 2, tls.name)
            else:
                self.model.set(iter, 2, "name here")

            self.model.set(iter, 3, self.markup_tensor(tls.T))
            self.model.set(iter, 4, self.markup_tensor(tls.L*rad2deg2))
            self.model.set(iter, 5, self.markup_tensor(tls.S*rad2deg))
        
    def timeout_cb(self):
        """Timer which drives the TLS animation.
        """
        self.animation_time += 0.005
        for tls_group in self.animation_list:
            tls_group.gl_tls.properties.update(time=self.animation_time)
        return gtk.TRUE

        

###############################################################################
### Hierarchical GTK Treeview control for browsing a list of
### mmLib.Structure objects
###

class StructureTreeControl(gtk.TreeView):
    """
    """

    def __init__(self, context):
        self.context = context
        self.struct_list = []
        
        gtk.TreeView.__init__(self)
        self.get_selection().set_mode(gtk.SELECTION_BROWSE)
        
        self.connect("row-activated", self.row_activated_cb)
        self.connect("button-release-event", self.button_release_event_cb)

        self.model = gtk.TreeStore(
            gobject.TYPE_BOOLEAN,   # 0: viewable
            gobject.TYPE_STRING)    # 1: data name
        self.set_model(self.model)

        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Structure", cell)
        column.add_attribute(cell, "text", 1)
        self.append_column(column)

    def row_activated_cb(self, tree_view, path, column):
        """Retrieve selected node, then call the correct set method for the
        type.
        """
        self.context.set_selected_struct_obj(self.resolv_path(path))
    
    def button_release_event_cb(self, tree_view, bevent):
        """
        """
        pass

    def resolv_path(self, path):
        """Get the item in the tree view at the specified path.
        """
        itemx = self.struct_list
        for i in path:
            itemx = itemx[i]
        return itemx
        
    def redraw(self):
        """Clear and refresh the view of the widget according to the
        self.struct_list
        """
        self.model.clear()
        for struct in self.struct_list:
            self.display_struct(struct)

    def display_struct(self, struct):
        iter1 = self.model.append(None)
        self.model.set(iter1, 1, str(struct))

        for chain in struct.iter_chains():
            iter2 = self.model.append(iter1)
            self.model.set(iter2, 1, str(chain))

            for frag in chain.iter_fragments():
                iter3 = self.model.append(iter2)
                self.model.set(iter3, 1, str(frag))

                for atm in frag.iter_all_atoms():
                    iter4 = self.model.append(iter3)
                    self.model.set(iter4, 1, str(atm))
                    
    def append_struct(self, struct):
        self.struct_list.append(struct)
        self.display_struct(struct)

    def remove_struct(self, struct):
        self.struct_list.remove(struct)
        self.redraw()



###############################################################################
### Application Window and Multi-Document tabs
### 
###



class StructureGUI(object):
    """This will become a notebook page when I get around to implementing
    a multi-tab interface.
    """

    def __init__(self, context):
        self.context = context        
    
        ## MAIN WIDGET
        self.hpaned = gtk.HPaned()
        self.hpaned.set_border_width(2)

        ## LEFT HALF: StructureTreeControl
        self.sw1 = gtk.ScrolledWindow()
        self.hpaned.add1(self.sw1)
        self.sw1.set_border_width(3)
        self.sw1.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        
        self.struct_ctrl = StructureTreeControl(self.context)
        self.sw1.add(self.struct_ctrl)

        ## RIGHT HALF: GtkGLViewer
        self.gtkglviewer = GtkGLViewer()
        self.hpaned.add2(self.gtkglviewer)

    def get_widget(self):
        return self.hpaned


class ViewCommands(list):
    def __init__(self):
        view_cmds = [
            { "menu path":       "/View/Carteasion Axes",
              "glstruct property": "axes_visible",
              "action":          100 },

            { "menu path":         "/View/Unit Cell",
              "glstruct property": "unit_cell_visible",
              "action":            101 },

            { "menu path":       "/View/Protein Main Chain",
              "glstruct property": "aa_main_chain_visible",
              "action":          102 },

            { "menu path":       "/View/Protein Side Chain",
              "glstruct property": "aa_side_chain_visible",
              "action":          103 },

            { "menu path":       "/View/DNA Main Chain",
              "glstruct property": "dna_main_chain_visible",
              "action":          104 },

            { "menu path":       "/View/DNA Side Chain",
              "glstruct property": "dna_side_chain_visible",
              "action":          105 },

            { "menu path":       "/View/HET Group",
              "glstruct property": "hetatm_visible",
              "action":          106 },

            { "menu path":       "/View/Water",
              "glstruct property": "water_visible",
              "action":          107},
            
            { "menu path":       "/View/Thermal Axes",
              "glstruct property": "U",
              "action":          108},
            ]

        list.__init__(self, view_cmds)

    def get_action(self, action):
        """Return the cmd dictionary by action number.
        """
        for cmd in self:
            if cmd["action"]==action:
                return cmd
        return None


class ColorCommands(list):
    def __init__(self):
        list.__init__(self, [
            { "menu path":  "/Colors/Color by Atom Type",
              "action":     100 },
            { "menu path":  "/Colors/Color by Chain",
              "action":     101 } ])

    def get_action(self, action):
        """Return the cmd dictionary by action number.
        """
        for cmd in self:
            if cmd["action"]==action:
                return cmd
        return None


class StructureContext(object):
    def __init__(self, struct, gl_struct):
        self.struct    = struct
        self.gl_struct = gl_struct


class MainWindow(object):
    def __init__(self, quit_notify_cb):
        self.struct_context_list = []
        self.sel_struct_context  = None
        self.sel_struct_obj      = None
        self.gl_prop_browser     = None
        self.view_cmds           = ViewCommands()
        self.color_cmds          = ColorCommands()
        self.quit_notify_cb      = quit_notify_cb

        ## dialog lists
        self.details_dialog_list = []
        self.tls_dialog_list     = []

        ## Create the toplevel window
        self.window = gtk.Window()
        self.set_title("")
        self.window.set_default_size(500, 400)
        self.window.connect('destroy', self.file_quit, self)

        table = gtk.Table(1, 4, gtk.FALSE)
        self.window.add(table)

        ## file menu bar
        file_menu_items = [
            ('/_File',            None,          None,                 0,'<Branch>'),
            ('/File/_New Window', None,          self.file_new_window, 0,'<StockItem>',gtk.STOCK_NEW),
            ('/File/_Open',       None,          self.file_open,       0,'<StockItem>',gtk.STOCK_OPEN),
            ('/File/sep1',        None,          None,                 0,'<Separator>'),
            ('/File/_Quit',      '<control>Q',   self.file_quit,       0,'<StockItem>',gtk.STOCK_QUIT) ]

        edit_menu_items = [
            ('/_Edit',            None,          None,                  0,'<Branch>'),
            ('/Edit/_Properties', None,          self.edit_properties,  0, None) ]

        view_menu_items = [
            ('/_View', None, None, 0, '<Branch>') ]
        
        for view_cmd in self.view_cmds:
            view_menu_items.append(
                (view_cmd["menu path"], None, self.view_menu, view_cmd["action"], '<CheckItem>') )

        color_menu_items = [
            ('/_Colors', None, None, 0, '<Branch>') ]
        
        for color_cmd in self.color_cmds:
            color_menu_items.append(
                (color_cmd["menu path"], None, self.color_menu, color_cmd["action"]) )
            
        tools_menu_items = [
            ('/_Tools', None, None, 0, '<Branch>'),
            ('/Tools/Selected Item Details...', None, self.tools_details,      0, None),
            ('/Tools/TLS Analysis...',          None, self.tools_tls_analysis, 0, None) ]

        help_menu_items = [
            ('/_Help',       None, None, 0, '<Branch>'),
            ('/Help/_About', None, None, 0, None) ]

        menu_items = file_menu_items +\
                     edit_menu_items +\
                     view_menu_items +\
                     color_menu_items +\
                     tools_menu_items +\
                     help_menu_items

        self.accel_group = gtk.AccelGroup()
        self.window.add_accel_group(self.accel_group)
        self.item_factory = gtk.ItemFactory(gtk.MenuBar, '<main>', self.accel_group)
        self.item_factory.create_items(menu_items)
    
        table.attach(self.item_factory.get_widget('<main>'),
                     # X direction              Y direction
                     0, 1,                      0, 1,
                     gtk.EXPAND | gtk.FILL,     0,
                     0,                         0)

        ## Toolbar
        self.hbox1 = gtk.HBox()
        table.attach(self.hbox1,
                     # X direction              Y direction
                     0, 1,                      1, 2,
                     gtk.EXPAND | gtk.FILL,     0,
                     0,                         0)

        self.hbox1.set_border_width(2)

        self.tb_label = gtk.Label("Current Selection:  ")
        self.hbox1.pack_start(self.tb_label, gtk.FALSE, gtk.FALSE, 0)

        self.select_label = gtk.Entry()
        self.select_label.set_editable(gtk.FALSE)
        self.hbox1.pack_start(self.select_label, gtk.TRUE, gtk.TRUE, 0)

        ## Create document        
        self.struct_gui = StructureGUI(self)
        table.attach(self.struct_gui.get_widget(),
                     # X direction           Y direction
                     0, 1,                   2, 3,
                     gtk.EXPAND | gtk.FILL,  gtk.EXPAND | gtk.FILL,
                     0,                      0)

        ## Create statusbar 
        self.hbox = gtk.HBox()
        table.attach(self.hbox,
                     # X direction           Y direction
                     0, 1,                   3, 4,
                     gtk.EXPAND | gtk.FILL,  0,
                     0,                      0)

        self.statusbar = gtk.Statusbar()
        self.hbox.pack_start(self.statusbar, gtk.TRUE, gtk.TRUE, 0)
        self.statusbar.set_has_resize_grip(gtk.FALSE)

        self.frame = gtk.Frame()
        self.hbox.pack_start(self.frame, gtk.FALSE, gtk.FALSE, 0)
        self.frame.set_border_width(3)

        self.progress = gtk.ProgressBar()
        self.frame.add(self.progress)
        self.progress.set_size_request(100, 0)

        self.window.show_all()

    def file_new_window(self, *args):
        """File->New Window
        """
        pass
        
    def file_open(self, *args):
        """File->Open
        """
        if hasattr(self, "file_selector"):
            self.file_selector.present()
            return
        self.file_selector = gtk.FileSelection("Select file to view");
        ok_button = self.file_selector.ok_button
        ok_button.connect("clicked", self.open_ok_cb, None)
        cancel_button = self.file_selector.cancel_button
        cancel_button.connect("clicked", self.open_cancel_cb, None)        
        self.file_selector.present()

    def destroy_file_selector(self):
        self.file_selector.destroy()
        del self.file_selector

    def open_ok_cb(self, *args):
        path = self.file_selector.get_filename()
        self.destroy_file_selector()
        self.load_file(path)

    def open_cancel_cb(self, *args):
        self.destroy_file_selector()

    def file_quit(self, *args):
        """File->Quit
        """
        self.quit_notify_cb(self.window, self)

    def edit_properties(self, *args):
        """Edit->Properties (GLPropertyBrowserDialog)
        """
        if self.gl_prop_browser==None:
            self.gl_prop_browser = GLPropertyBrowserDialog(
                self.window,
                self.struct_gui.gtkglviewer)

            self.gl_prop_browser.connect(
                "destroy",
                self.gl_prop_browser_destroy)

        self.gl_prop_browser.present()

    def edit_properties_gl_object(self, gl_object):
        """Opens/Presents the GLPropertyBrowser Dialog and selects
        gl_object for editing.
        """
        self.edit_properties()
        self.gl_prop_browser.select_gl_object(gl_object)

    def gl_prop_browser_destroy(self, widget):
        """Callback when the GLProeriesBrowser is destroyed.
        """
        self.gl_prop_browser = None

    def gl_prop_browser_rebuild_gl_object_tree(self):
        """This rebuilds the GLPropertiesBrowser when any
        GLObject is added or removed from it.
        """
        if self.gl_prop_browser!=None:
            self.gl_prop_browser.rebuild_gl_object_tree()

    def tools_details(self, *args):
        """Tools->Selected Item Details
        """
        if self.sel_struct_obj == None:
            self.error_dialog("No Structure Selected.")
            return
        details = StructDetailsDialog(self)
        details.set_struct_obj(self.sel_struct_obj)
        details.present()

    def tools_tls_analysis(self, *args):
        """Tools->TLS Analysis
        """

        if self.sel_struct_context==None:
            return
        tls = TLSDialog(
            main_window    = self,
            struct_context = self.sel_struct_context)
        tls.present()

    def view_menu(self, callback_action, widget):
        """View->[All Items]
        """
        if self.sel_struct_context==None:
            return
        view_cmd  = self.view_cmds.get_action(callback_action)
        property  = view_cmd["glstruct property"]
        menu_item = self.item_factory.get_item(view_cmd["menu path"])
        if menu_item.get_active() == gtk.TRUE:
            visible = True
        else:
            visible = False
        self.sel_struct_context.gl_struct.properties.update(**{property: visible})            

    def color_menu(self, callback_action, widget):
        """Color->[All Items]
        """
        if self.sel_struct_context==None:
            return
        color_cmd = self.color_cmds.get_action(callback_action)

        if callback_action==100:
            self.sel_struct_context.gl_struct.properties.update(color=None)

        elif callback_action==101: 
            gl_struct = self.sel_struct_context.gl_struct

            color_list = [(1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(1.,1.,0.),(0.,1.,1.),(1.,0.,1.),(1.,1.,1.)]
            colori = 0

            chain_dict = {}
            for gl_object in gl_struct.glo_iter_children():
                if isinstance(gl_object, GLChain):
                    chain_dict[gl_object.chain.chain_id] = gl_object

            chain_ids = chain_dict.keys()
            chain_ids.sort()
            
            for chain_id in chain_ids:
                gl_chain = chain_dict[chain_id]
                
                try:
                    color = color_list[colori]
                except IndexError:
                    color = color_list[-1]
                else:
                    colori += 1
                
                gl_chain.properties.update(color=color)

    def set_title(self, title):
        self.window.set_title("Viewer: %s" % (title[:50]))

    def set_statusbar(self, text):
        self.statusbar.pop(0)
        self.statusbar.push(0, text)

    def error_dialog(self, text):
        """Display modeal error dialog box containing the error text.
        """
        dialog = gtk.MessageDialog(
            self.window,
            gtk.DIALOG_DESTROY_WITH_PARENT,
            gtk.MESSAGE_ERROR,
            gtk.BUTTONS_CLOSE,
            text)
        
        dialog.run()
        dialog.destroy()


    def load_file(self, path):
        """Loads the structure file specified in the path.
        """
        self.set_title(path)
        self.set_statusbar("Loading: %s" % (path))

        struct = LoadStructure(
            fil              = path,
            update_cb        = self.update_cb,
            build_properties = ("sequence","bonds"))

        struct.path = path
        
        gl_struct = self.struct_gui.gtkglviewer.glv_add_struct(struct)

        struct_context = StructureContext(struct, gl_struct)
        self.struct_context_list.append(struct_context)
        self.struct_gui.struct_ctrl.append_struct(struct_context.struct)
        if self.sel_struct_context==None:
            self.set_selected_struct_obj(struct)

        self.set_statusbar("")
        self.progress.set_fraction(0.0)
        return gtk.FALSE
    
    def update_cb(self, percent):
        """Callback for file loading code to inform the GUI of how
        of the file has been read
        """
        self.progress.set_fraction(percent/100.0)
        while gtk.events_pending():
            gtk.main_iteration(gtk.TRUE)

    def set_selected_struct_obj(self, struct_obj):
        """Set the currently selected structure item.
        """
        self.sel_struct_obj = struct_obj
        
        ## nothing selected
        if struct_obj==None:
            self.sel_struct_context = None
            self.select_label.set_text("")

            for view_cmd in self.view_cmds:
                menu_item = self.item_factory.get_item(view_cmd["menu path"])
                menu_item.set_active(view_cmd["checked"])

        else:
            self.select_label.set_text(str(self.sel_struct_obj))

            struct = struct_obj.get_structure()
            self.sel_struct_context = self.get_struct_context(struct)
            self.set_selected_struct_context(self.sel_struct_context)

    def set_selected_struct_context(self, struct_context):
        """Sets the current struct_context and updates the context
        sensitive GUI widgets.
        """
        for view_cmd in self.view_cmds:
            property  = view_cmd["glstruct property"]
            menu_item = self.item_factory.get_item(view_cmd["menu path"])
            if struct_context.gl_struct.properties[property]==False:
                menu_item.set_active(gtk.FALSE)
            else:
                menu_item.set_active(gtk.TRUE)

    def get_struct_context(self, struct):
        """Returns the struct_context containing struct.
        """
        for struct_context in self.struct_context_list:
            if struct_context.struct==struct:
                return struct_context
        return None


def main(path = None):
    main_window_list = []

    def quit_notify_cb(window, mw):
        main_window_list.remove(mw)
        if len(main_window_list) < 1:
            gtk.main_quit()

    mw = MainWindow(quit_notify_cb)
    main_window_list.append(mw)

    if path:
        gobject.timeout_add(25, mw.load_file, path)

    gtk.main()


if __name__ == "__main__":
    import sys

    try:
        main(sys.argv[1])
    except IndexError:
        main()
