# Copyright (C) 2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
# See: https://spdx.org/licenses/
import unittest
import typing as ty

import numpy as np

from lava.magma.core.process.process import AbstractProcess
from lava.magma.core.process.variable import Var
from lava.magma.core.process.ports.ports import InPort, OutPort
from lava.magma.core.decorator import has_models, requires
from lava.magma.core.resources import CPU
from lava.magma.core.model.py.model import AbstractPyProcessModel
from lava.magma.core.model.py.type import LavaPyType
from lava.magma.core.model.py.ports import PyInPort, PyOutPort

from lava.magma.compiler.utils import VarInitializer, PortInitializer
from lava.magma.compiler.builder import PyProcessBuilder
from lava.magma.compiler.channels.interfaces import AbstractCspPort


# A test PyProcessModel with corresponding LavaPyTypes for each Proc Port or Var
# Vars and Ports should have type annotations such that linter does not throw
# warnings in run(..) method because it otherwise assumes the type of the
# instance variables (created by Compiler) for every class variable is a
# LavaPyType.
@requires(CPU)
class ProcModel(AbstractPyProcessModel):
    in_port: PyInPort = LavaPyType(PyInPort.VEC_DENSE, int, 8)
    v1_scalar: int = LavaPyType(int, int, 27)
    v2_scalar_init: int = LavaPyType(int, int, 27)
    v3_tensor_broadcast: np.ndarray = LavaPyType(np.ndarray, np.int32, 6)
    v4_tensor = LavaPyType(np.ndarray, np.int32, 6)
    out_port: PyOutPort = LavaPyType(PyOutPort.VEC_DENSE, int, 8)

    def run(self):
        """Every PyProcModel must implement a run(..) method. Here we perform
        just some fake computation to demonstrate initialized Vars can be used.
        """
        return self.v1_scalar + 1


# A test Process with a variety of Ports and Vars of different shapes,
# with and without initial values that may require broadcasting or not
@has_models(ProcModel)
class Proc(AbstractProcess):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.in_port = InPort((2, 1))
        self.v1_scalar = Var((1,))
        self.v2_scalar_init = Var((1,), init=2)
        self.v3_tensor_broadcast = Var((2, 3), init=10)
        self.v4_tensor = Var((3, 2), init=[[1, 2], [3, 4], [5, 6]])
        self.out_port = OutPort((3, 2))


# A fake CspPort just to test ProcBuilder
class FakeCspPort(AbstractCspPort):
    def __init__(self, name="mock"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def shape(self) -> ty.Tuple[int, ...]:
        return (1, 2)

    @property
    def d_type(self) -> np.dtype:
        return np.int32.dtype

    @property
    def size(self) -> int:
        return 32

    def start(self):
        pass

    def join(self):
        pass


# A correct ProcessModel
@requires(CPU)
class ProcModelForLavaPyType0(AbstractPyProcessModel):
    port: PyInPort = LavaPyType(PyInPort.VEC_DENSE, int)


# A wrong ProcessModel with completely wrong type
@requires(CPU)
class ProcModelForLavaPyType1(AbstractPyProcessModel):
    port: PyInPort = LavaPyType(123, int)  # type: ignore


# A wrong ProcessModel with wrong syb type
@requires(CPU)
class ProcModelForLavaPyType2(AbstractPyProcessModel):
    port: PyInPort = LavaPyType(PyInPort, int)


# A wrong ProcessModel with wrong port type
@requires(CPU)
class ProcModelForLavaPyType3(AbstractPyProcessModel):
    port: PyInPort = LavaPyType(PyOutPort, int)


# Another Process for LavaPyType validation
@has_models(ProcModelForLavaPyType0, ProcModelForLavaPyType1,
            ProcModelForLavaPyType2, ProcModelForLavaPyType3)
class ProcForLavaPyType(AbstractProcess):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.port = InPort((1, ))


class TestPyProcessBuilder(unittest.TestCase):
    """ProcessModels are not not created directly but through a corresponding
    PyProcessBuilder. Therefore, we test both classes together."""

    def test_constructor(self):
        """Checks PyProcessBuilder can be constructed."""

        b = PyProcessBuilder(ProcModel, 0)

        self.assertIsInstance(b, PyProcessBuilder)

    def test_set_variables_and_ports(self):
        """Check variables and ports can be set."""

        # Create a new ProcBuilder
        b = PyProcessBuilder(ProcModel, 0)

        # Create Process for which we want to build PyProcModel
        proc = Proc()

        # Normally, the Compiler would create VarInitializers for every
        # Process Var holding only its name, shape and initial value
        v = [VarInitializer(v.name, v.shape, v.init, v.id) for v in proc.vars]
        # Similarly, the Compiler would create PortInitializers from all
        # ports holding only its name and shape
        ports = list(proc.in_ports) + list(proc.out_ports)
        py_ports = [
            PortInitializer(
                pt.name, pt.shape, getattr(ProcModel, pt.name).d_type,
                pt.__class__.__name__, 32
            )
            for pt in ports
        ]
        # Later, the Runtime, would normally create CspPorts that implements
        # the actual message passing via channels between PyPorts. Here we
        # just create some fake CspPorts for each PyPort.
        csp_ports = []
        for py_port in py_ports:
            csp_ports.append(FakeCspPort(py_port.name))

        # During compilation, the Compiler creates and then sets
        # VarInitializers and PyPortInitializers
        b.set_variables(v)
        b.set_py_ports(py_ports)
        # The Runtime sets CspPorts
        b.set_csp_ports(csp_ports)

        # All the objects are converted into dictionaries to retrieve them by
        # name
        self.assertEqual(list(b.vars.values()), v)
        self.assertEqual(list(b.py_ports.values()), py_ports)
        self.assertEqual(list(b.csp_ports.values()), csp_ports)
        self.assertEqual(b.vars["v1_scalar"], v[0])
        self.assertEqual(b.py_ports["in_port"], py_ports[0])
        self.assertEqual(b.csp_ports["out_port"], csp_ports[1])

    def test_setting_non_existing_var(self):
        """Checks that setting Var not defined in ProcModel fails. Same will
        apply for Ports"""

        # Lets create a ProcBuilder and Proc
        b = PyProcessBuilder(ProcModel, 0)
        proc = Proc()

        # Also generate list of VarInitializers from lava.proc Vars...
        v = [VarInitializer(v.name, v.shape, v.init, v.id) for v in proc.vars]
        # ...but let's pretend Proc would define another Var
        v.append(VarInitializer("AnotherVar", (1, 2, 3), 100, 0))

        # This fails because there exists no LavaPyType for 'AnotherVar' in
        # ProcModel
        with self.assertRaises(AssertionError):
            b.set_variables(v)

    def test_check_all_vars_and_ports_set(self):
        """Checks that all Vars and Ports for which LavaPyType exists must
        be set."""

        # Lets create a ProcBuilder and Proc with Var- and PortInitializers
        b = PyProcessBuilder(ProcModel, 0)
        proc = Proc()
        v = [VarInitializer(v.name, v.shape, v.init, v.id) for v in proc.vars]
        ports = list(proc.in_ports) + list(proc.out_ports)
        py_ports = [
            PortInitializer(
                pt.name, pt.shape, getattr(ProcModel, pt.name).d_type,
                pt.__class__.__name__, 32
            )
            for pt in ports
        ]

        # But do not assign all of them to builder
        b.set_variables(v[:-1])
        b.set_py_ports(py_ports[:-1])

        # Before a builder it deployed to a remote node, the compiler will
        # check if Var- and PortInitializers have been set for all LavaPyTypes.
        # Thus his will fails.
        with self.assertRaises(AssertionError):
            b.check_all_vars_and_ports_set()

        # But when we set all of them...
        b.set_variables([v[-1]])
        b.set_py_ports([py_ports[-1]])

        # ... the check will pass
        b.check_all_vars_and_ports_set()

    def test_check_lava_py_types(self):
        """Checks identification of illegal LavaPyType settings.

        All ProcModels tested here implement ProcForLavaPyType which has one
        InPort called 'port'
        """

        # Create univeral PortInitializer reflecting the 'port' in
        # ProcForLavaPyType
        pi = PortInitializer("port", (1,), np.intc, "InPort", 32)

        # Create PortInitializer for correct LavaPyType(PyInPort.VEC_DENSE, int)
        b = PyProcessBuilder(ProcModelForLavaPyType0, 0)
        b.set_py_ports([pi])

        # This one is legal
        b.check_lava_py_types()

        # Create PortInitializer for wrong LavaPyType(123, int)
        b = PyProcessBuilder(ProcModelForLavaPyType1, 1)
        b.set_py_ports([pi])

        # This one fails because '123' is not a type
        with self.assertRaises(AssertionError):
            b.check_lava_py_types()

        # Create PortInitializer for wrong LavaPyType(PyInPort, int)
        b = PyProcessBuilder(ProcModelForLavaPyType2, 2)
        b.set_py_ports([pi])

        # This one fails because 'PyInPort' is not a strict subtype of
        # 'PyInPort'
        with self.assertRaises(AssertionError):
            b.check_lava_py_types()

        # Create PortInitializer for wrong LavaPyType(PyOutPort, int)
        b = PyProcessBuilder(ProcModelForLavaPyType3, 3)
        b.set_py_ports([pi])

        # This one fails because 'PyOutPort' is not a strict sub-type at all
        # of PyInPort
        with self.assertRaises(AssertionError):
            b.check_lava_py_types()

    def test_build(self):
        """Checks building of ProcessModel by builder."""

        # Lets create a ProcBuilder and Proc with Var- and PortInitializers
        # and fake CspPorts so ProcModel can be built
        b = PyProcessBuilder(ProcModel, 0)

        proc = Proc()
        v = [VarInitializer(v.name, v.shape, v.init, v.id) for v in proc.vars]

        ports = list(proc.in_ports) + list(proc.out_ports)
        py_ports = [
            PortInitializer(
                pt.name, pt.shape, getattr(ProcModel, pt.name).d_type,
                pt.__class__.__name__, 32
            )
            for pt in ports
        ]

        csp_ports = []
        for py_port in py_ports:
            csp_ports.append(FakeCspPort(py_port.name))

        # Set all Var-, PortInitializers and fake CspPorts
        b.set_variables(v)
        b.set_py_ports(py_ports)
        b.set_csp_ports(csp_ports)

        # Before we build, we should make sure all vars and ports are set and
        # that there's a CSP port for every PyPort
        b.check_all_vars_and_ports_set()

        # Building the ProcModel will initialize Vars and Ports on ProcModel
        # instance
        pm = b.build()

        # Thus the ProcModel instance should have PyPort attributes as
        # defined by by the Process and ProcessModel class
        import lava.magma.core.model.py.ports as pts

        self.assertTrue(hasattr(pm, "in_port"))
        self.assertIsInstance(pm.in_port, pts.PyInPortVectorDense)
        self.assertTrue(hasattr(pm, "out_port"))
        self.assertIsInstance(pm.out_port, pts.PyOutPortVectorDense)
        # And these ports should have the specified shape
        self.assertEqual(pm.in_port._shape, (2, 1))
        self.assertEqual(pm.out_port._shape, (3, 2))

        # Similarly, Var attributes should exist with all initial values
        # being broadcast to required shape if necessary
        self.assertEqual(pm.v1_scalar, 0)
        self.assertEqual(pm.v2_scalar_init, 2)
        self.assertTrue(
            np.array_equal(
                pm.v3_tensor_broadcast, np.ones((2, 3), dtype=np.int32) * 10
            )
        )
        self.assertTrue(
            np.array_equal(
                pm.v4_tensor, np.array([[1, 2], [3, 4], [5, 6]], dtype=np.int32)
            )
        )

        # In addition, private attribute for variables precisions got created
        # following the naming convention "_<var_name>_p":
        self.assertEqual(pm._v1_scalar_p, 27)
        self.assertEqual(pm._v2_scalar_init_p, 27)
        self.assertEqual(pm._v3_tensor_broadcast_p, 6)
        self.assertEqual(pm._v4_tensor_p, 6)

        # Just to make sure the generated Vars are really usable, we can call
        # the run(..) method:
        self.assertEqual(pm.run(), 1)

    def test_build_with_dangling_ports(self):
        """Checks that not all ports must be connected, i.e. ports can be
        left dangling."""

        # First create a process with no OutPorts
        proc_with_no_out_ports = Proc()
        v = [VarInitializer(v.name, v.shape, v.init, v.id)
             for v in proc_with_no_out_ports.vars]

        ports = \
            list(proc_with_no_out_ports.in_ports) + \
            list(proc_with_no_out_ports.out_ports)
        py_ports = [
            PortInitializer(
                pt.name, pt.shape, getattr(ProcModel, pt.name).d_type,
                pt.__class__.__name__, 32
            )
            for pt in ports
        ]

        csp_ports = []
        for py_port in list(proc_with_no_out_ports.in_ports):
            csp_ports.append(FakeCspPort(py_port.name))

        b_with_no_out_ports = PyProcessBuilder(ProcModel, 0)
        b_with_no_out_ports.set_variables(v)
        b_with_no_out_ports.set_py_ports(py_ports)
        b_with_no_out_ports.set_csp_ports(csp_ports)

        # Next create a process with no InPorts
        proc_with_no_in_ports = Proc()
        v = [VarInitializer(v.name, v.shape, v.init, v.id)
             for v in proc_with_no_in_ports.vars]

        ports = \
            list(proc_with_no_in_ports.in_ports) + \
            list(proc_with_no_in_ports.out_ports)
        py_ports = [
            PortInitializer(
                pt.name, pt.shape, getattr(ProcModel, pt.name).d_type,
                pt.__class__.__name__, 32
            )
            for pt in ports
        ]

        csp_ports = []
        for py_port in list(proc_with_no_in_ports.out_ports):
            csp_ports.append(FakeCspPort(py_port.name))

        b_with_no_in_ports = PyProcessBuilder(ProcModel, 0)
        b_with_no_in_ports.set_variables(v)
        b_with_no_in_ports.set_py_ports(py_ports)
        b_with_no_in_ports.set_csp_ports(csp_ports)

        # Validate builders
        b_with_no_out_ports.check_all_vars_and_ports_set()
        b_with_no_in_ports.check_all_vars_and_ports_set()

        # Then build them
        pm_with_no_out_ports = b_with_no_out_ports.build()
        pm_with_no_in_ports = b_with_no_in_ports.build()

        # Validate that the Process with no OutPorts indeed has no output
        # CspPort
        self.assertIsInstance(
            pm_with_no_out_ports.in_port._csp_port, FakeCspPort)
        self.assertEqual(pm_with_no_out_ports.out_port._csp_port, None)

        # Validate that the Process with no InPorts indeed has no input
        # CspPort
        self.assertEqual(pm_with_no_in_ports.in_port._csp_port, None)
        self.assertIsInstance(
            pm_with_no_in_ports.out_port._csp_port, FakeCspPort)


if __name__ == "__main__":
    unittest.main()
