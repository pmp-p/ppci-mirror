#!/usr/bin/python

"""
    Debug user interface for debugging.
"""

import sys
import logging

from qtwrapper import QtGui, QtCore, QtWidgets, pyqtSignal, get_icon
from qtwrapper import abspath, Qt

import ppci.api
import ppci.common
from ppci.binutils.dbg import Debugger
from ppci.binutils import debuginfo

from codeedit import CodeEdit
from logview import LogView as BuildOutput
from regview import RegisterView
from memview import MemoryView
from disasm import Disassembly
from dbgtoolbar import DebugToolbar
from connectiontoolbar import ConnectionToolbar
from linux64debugserver import LinuxDebugDriver


class BuildErrors(QtWidgets.QTreeView):
    sigErrorSelected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        model = QtGui.QStandardItemModel()
        self.setModel(model)
        self.clicked.connect(self.itemSelected)
        self.errorIcon = get_icon('error.png')
        self.model = QtGui.QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Message', 'Row', 'Column'])
        self.header().setStretchLastSection(True)
        self.setModel(self.model)

    def setErrorList(self, errorlist):
        c = self.model.rowCount()
        self.model.removeRows(0, c)
        for e in errorlist:
            item = QtGui.QStandardItem(self.errorIcon, str(e.msg))
            item.setData(e)
            row = str(e.loc.row) if e.loc else ''
            irow = QtGui.QStandardItem(row)
            irow.setData(e)
            col = str(e.loc.col) if e.loc else ''
            icol = QtGui.QStandardItem(col)
            icol.setData(e)
            self.model.appendRow([item, irow, icol])
        for i in range(3):
            self.resizeColumnToContents(i)

    def itemSelected(self, index):
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        err = item.data()
        self.sigErrorSelected.emit(err)


class VariableModel(QtCore.QAbstractItemModel):
    """ Model that contains a view on the current values of variables """
    def __init__(self, debugger):
        super().__init__()
        self.debugger = debugger
        self.debugger.state_event.subscribe(self.on_state_changed)
        print(self.debugger.obj)
        self.headers = ('Name', 'Value', 'Type')

    def on_state_changed(self):
        if self.debugger.is_halted:
            from_index = self.index(0, 1)
            variables = self.debugger.obj.debug_info.variables
            to_index = self.index(len(variables) - 1, 1)
            self.dataChanged.emit(from_index, to_index)

    def rowCount(self, parent):
        variables = self.debugger.obj.debug_info.variables
        if not parent.isValid():
            # Root level:
            return len(variables)
        node = parent.internalPointer()
        print(node)
        if isinstance(node, debuginfo.DebugVariable):
            pass
        return 0

    def columnCount(self, parent):
        if parent.isValid():
            return 0
        return len(self.headers)

    def index(self, row, column, parent=QtCore.QModelIndex()):
        variables = self.debugger.obj.debug_info.variables
        if not parent.isValid():
            # Root stuff:
            var = variables[row]
            return self.createIndex(row, column, var)
        raise RuntimeError('Not possible!')

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        return QtCore.QModelIndex()

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]

    def data(self, index, role):
        if not index.isValid():
            return
        row, col = index.row(), index.column()
        variables = self.debugger.obj.debug_info.variables
        if role == Qt.DisplayRole:
            var = variables[row]
            if col == 0:
                return var.name
            elif col == 1:
                return ''
            elif col == 2:
                return str(var.typ)
            else:
                raise NotImplementedError()


class Locals(QtWidgets.QTreeView):
    def __init__(self, debugger):
        super().__init__()
        model = VariableModel(debugger)
        self.setModel(model)


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('About')
        l = QtWidgets.QVBoxLayout(self)
        txt = QtWidgets.QTextEdit(self)
        txt.setReadOnly(True)
        aboutText = "ppci debugger"
        txt.append(aboutText)
        l.addWidget(txt)
        but = QtWidgets.QPushButton('OK')
        but.setDefault(True)
        but.clicked.connect(self.close)
        l.addWidget(but)


class DebugUi(QtWidgets.QMainWindow):
    """ Provide a nice gui for this debugger """
    def __init__(self, debugger, parent=None):
        super().__init__(parent)
        self.debugger = debugger
        self.debugger.state_event.subscribe(self.on_state_changed)
        self.logger = logging.getLogger('dbgui')
        self.setWindowTitle('PPCI DBGUI')

        # Create menus:
        mb = self.menuBar()
        self.fileMenu = mb.addMenu('File')
        self.viewMenu = mb.addMenu('View')
        self.helpMenu = mb.addMenu('Help')

        # Create mdi area:
        self.mdiArea = QtWidgets.QMdiArea()
        self.mdiArea.setViewMode(QtWidgets.QMdiArea.TabbedView)
        self.mdiArea.setTabsClosable(True)
        self.mdiArea.setTabsMovable(True)
        self.setCentralWidget(self.mdiArea)

        # Create components:
        def addComponent(name, widget):
            dw = QtWidgets.QDockWidget(name)
            dw.setWidget(widget)
            dw.setObjectName(name)
            self.addDockWidget(Qt.RightDockWidgetArea, dw)
            self.viewMenu.addAction(dw.toggleViewAction())
            return widget

        self.buildOutput = addComponent('Build output', BuildOutput())
        self.builderrors = addComponent('Build errors', BuildErrors())
        self.regview = addComponent('Registers', RegisterView(debugger))
        self.memview = addComponent('Memory', MemoryView(debugger))
        self.disasm = addComponent('Disasm', Disassembly(debugger))
        self.locals = addComponent('Locals', Locals(debugger))
        self.ctrlToolbar = DebugToolbar(debugger)
        self.addToolBar(self.ctrlToolbar)
        self.ctrlToolbar.setObjectName('debugToolbar')
        self.aboutDialog = AboutDialog()

        # Create actions:
        def addMenuEntry(name, menu, callback, shortcut=None):
            a = QtWidgets.QAction(name, self)
            menu.addAction(a)
            a.triggered.connect(callback)
            if shortcut:
                a.setShortcut(QtGui.QKeySequence(shortcut))

        addMenuEntry(
            "Open", self.fileMenu, self.openFile,
            shortcut=QtGui.QKeySequence.Open)

        self.helpAction = QtWidgets.QAction('Help', self)
        self.helpAction.setShortcut(QtGui.QKeySequence('F1'))
        self.helpMenu.addAction(self.helpAction)
        addMenuEntry('About', self.helpMenu, self.aboutDialog.open)

        addMenuEntry(
            'Cascade windows', self.viewMenu, self.mdiArea.cascadeSubWindows)
        addMenuEntry(
            'Tile windows', self.viewMenu, self.mdiArea.tileSubWindows)
        self.statusBar()

        # Load settings:
        self.settings = QtCore.QSettings('windelsoft', 'lcfoside')
        self.loadSettings()

    # File handling:
    def openFile(self):
        filename = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open C3 file...", "*.c3",
            "C3 source files (*.c3)")
        if filename:
            self.load_file(filename[0])

    def load_file(self, filename):
        print(filename)
        ce = self.new_code_edit()
        try:
            with open(filename) as f:
                ce.Source = f.read()
                ce.FileName = filename
            return ce
        except Exception as e:
            print('exception opening file:', e)

    # MDI:
    def new_code_edit(self):
        ce = CodeEdit()
        ce.breakpointChanged.connect(self.toggle_breakpoint)
        w = self.mdiArea.addSubWindow(ce)
        self.mdiArea.setActiveSubWindow(w)
        ce.showMaximized()
        return ce

    def activeMdiChild(self):
        aw = self.mdiArea.activeSubWindow()
        if aw:
            return aw.widget()

    def find_mdi_child(self, filename):
        for sub_window in self.mdiArea.subWindowList():
            wid = sub_window.widget()
            if wid.filename == filename:
                self.mdiArea.setActiveSubWindow(sub_window)
                return wid

    # Settings:
    def loadSettings(self):
        if self.settings.contains('mainwindowstate'):
            self.restoreState(self.settings.value('mainwindowstate'))
        if self.settings.contains('mainwindowgeometry'):
            self.restoreGeometry(self.settings.value('mainwindowgeometry'))

    def closeEvent(self, ev):
        self.settings.setValue('mainwindowstate', self.saveState())
        self.settings.setValue('mainwindowgeometry', self.saveGeometry())

    def toggle_breakpoint(self, filename, row, state):
        if state:
            self.debugger.set_breakpoint(filename, row)
        else:
            self.debugger.clear_breakpoint(filename, row)

    # Error handling:
    def show_loc(self, filename, row, col):
        """ Show a location in some source file """
        # Activate, or load file:
        ce = self.find_mdi_child(filename)
        if not ce:
            ce = self.load_file(filename)
        if not ce:
            print('fail to load ', filename)
            return
        ce.set_current_row(row)
        ce.setFocus()

    def on_state_changed(self):
        """ When the debugger is halted or started again .. """
        if self.debugger.is_halted:
            res = self.debugger.find_pc()
            if res:
                filename, row = res
                self.show_loc(filename, row, 1)


if __name__ == '__main__':
    # dut = '../../test/listings/testsamplesTestSamplesOnX86Linuxtestswdiv.elf'

    # Hello:
    #dut = '../../examples/linux64/hello/hello'
    #obj = '../../examples/linux64/hello/hello.elf'

    # Snake:
    dut = '../../examples/linux64/snake/snake'
    obj = '../../examples/linux64/snake/snake.elf'

    logging.basicConfig(format=ppci.common.logformat, level=logging.DEBUG)
    app = QtWidgets.QApplication(sys.argv)
    # TODO: couple this other way, and make it configurable:
    linux_specific = LinuxDebugDriver()
    linux_specific.go_for_it([dut])
    debugger = Debugger('x86_64', linux_specific)
    debugger.load_symbols(obj)
    ui = DebugUi(debugger)
    ui.show()
    ui.logger.info('IDE started')
    app.exec_()
    debugger.shutdown()
