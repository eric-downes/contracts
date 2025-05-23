import collections
import sys

# In Python 3.3+, many abstract base classes moved to collections.abc
if sys.version_info >= (3, 3):
    from collections import abc as collections_abc
else:
    collections_abc = collections


def ist(C):
    def f(x):
        f.__name__ = 'isinstance_of_%s' % C.__name__
        if not isinstance(x, C):
            raise ValueError('Value is not an instance of %s.' % C.__name__)
    return f


def m_new_contract(name, f):
    from contracts.library.extensions import CheckCallable
    from contracts.library.extensions import Extension
    Extension.registrar[name] = CheckCallable(f)
    

m_new_contract('Container', ist(collections_abc.Container))
# todo: Iterable(x)
m_new_contract('Iterable', ist(collections_abc.Iterable))

m_new_contract('Hashable', ist(collections_abc.Hashable))



m_new_contract('Iterator', ist(collections_abc.Iterator))
m_new_contract('Sized', ist(collections_abc.Sized))
m_new_contract('Callable', callable)  # Use built-in callable function instead
m_new_contract('Sequence', ist(collections_abc.Sequence))
m_new_contract('Set', ist(collections_abc.Set))
m_new_contract('MutableSequence', ist(collections_abc.MutableSequence))
m_new_contract('MutableSet', ist(collections_abc.MutableSet))
m_new_contract('Mapping', ist(collections_abc.Mapping))
m_new_contract('MutableMapping', ist(collections_abc.MutableMapping))
#new_contract('MappingView', ist(collections.MappingView))
#new_contract('ItemsView', ist(collections.ItemsView))
#new_contract('ValuesView', ist(collections.ValuesView))


# Not a lambda to have better messages
def is_None(x): 
    return x is None

m_new_contract('None', is_None)
m_new_contract('NoneType', is_None)
