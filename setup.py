import os

from setuptools import setup, find_packages

description = (
    'PyContracts is a Python package that allows to declare '
    'constraints on function parameters and return values. '
    'Contracts can be specified using Python3 annotations, '
    'in a decorator, or inside a docstring :type: and :rtype: tags. '
    'PyContracts supports a basic type system, variables binding, '
    'arithmetic constraints, and has several specialized '
    'contracts (notably for Numpy arrays), as well as an extension API.')


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


long_description = read('README.rst')


def get_version(filename):
    import ast
    version = None
    with open(filename) as f:
        for line in f:
            if line.startswith('__version__'):
                version = ast.parse(line).body[0].value.s
                break
        else:
            raise ValueError('No version found in %r.' % filename)
    if version is None:
        raise ValueError(filename)
    return version


version = get_version(filename='src/contracts/__init__.py')

setup(name='PyContracts',
      author="Andrea Censi",
      author_email="censi@mit.edu",
      url='http://andreacensi.github.com/contracts/',

      description=description,
      long_description=long_description,
      keywords="type checking, value checking, contracts",
      license="LGPL",

      version=version,
      download_url='http://github.com/AndreaCensi/contracts/tarball/%s' % version,

      package_dir={'': 'src'},
      packages=find_packages('src'),
      install_requires=['pyparsing>=3.0.0', 'decorator', 'six', 'future'],
      tests_require=['pytest>=7.0.0', 'pytest-cov>=6.0.0', 'numpy'],
      python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*',
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
          'Topic :: Software Development :: Quality Assurance',
          'Topic :: Software Development :: Documentation',
          'Topic :: Software Development :: Testing',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
          'Programming Language :: Python :: 3.10',
          'Programming Language :: Python :: 3.11',
          'Programming Language :: Python :: 3.12',
      ],
      entry_points={},
      )
