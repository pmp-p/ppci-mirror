""" A compiler for ARM, X86, MSP430, xtensa and more implemented in
pure Python.

Example usage:

>>> from ppci.arch.x86_64 import instructions, registers
>>> pop = instructions.Pop(registers.rbx)
>>> pop.encode()
b'['

"""

import sys

# Define version here. Used in docs, and setup script:
__version__ = '0.5.4'

# Assert python version:
assert sys.version_info.major == 3, "Needs to be run in python version 3.x"
