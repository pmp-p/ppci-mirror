""" C scoping functions """
from . import nodes


class Scope:
    """ A variable scope """
    def __init__(self, parent=None):
        self.parent = parent
        # Different namespaces in this scope:
        self.var_map = {}
        self.tags = {}
        self.labels = {}

    def is_defined(self, name, all_scopes=True):
        """ Check if the name is defined """
        if name in self.var_map:
            return True
        elif self.parent and all_scopes:
            return self.parent.is_defined(name)
        else:
            return False

    def insert(self, variable: nodes.NamedDeclaration):
        """ Insert a variable into the current scope """
        assert isinstance(variable, nodes.NamedDeclaration)
        self.var_map[variable.name] = variable

    def get_tag(self, name):
        """ Get a struct by tag """
        return self.tags[name]

    def get(self, name):
        """ Get the symbol with the given name """
        if name in self.var_map:
            return self.var_map[name]
        elif self.parent:
            return self.parent.get(name)
        else:
            raise KeyError(name)