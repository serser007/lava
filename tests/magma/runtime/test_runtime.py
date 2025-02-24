import typing as ty
import unittest

from lava.magma.compiler.executable import Executable
from lava.magma.core.resources import HeadNode
from lava.magma.core.run_conditions import RunSteps, AbstractRunCondition
from lava.magma.compiler.node import Node, NodeConfig
from lava.magma.runtime.runtime import Runtime


class TestRuntime(unittest.TestCase):
    def test_runtime_creation(self):
        exe: Executable = Executable()
        run_cond: AbstractRunCondition = RunSteps(num_steps=10)
        runtime: Runtime = Runtime(run_cond=run_cond, exe=exe)
        expected_type: ty.Type = Runtime
        assert isinstance(
            runtime, expected_type
        ), f"Expected type {expected_type} doesn't match {(type(runtime))}"

    def test_executable_node_config_assertion(self):
        exec: Executable = Executable()
        run_cond: AbstractRunCondition = RunSteps(num_steps=10)

        runtime1: Runtime = Runtime(run_cond, exec)
        with self.assertRaises(AssertionError):
            runtime1.initialize()

        node: Node = Node(HeadNode, [])
        exec.node_configs.append(NodeConfig([node]))
        runtime2: Runtime = Runtime(run_cond, exec)
        runtime2.initialize()
        expected_type: ty.Type = Runtime
        assert isinstance(
            runtime2, expected_type
        ), f"Expected type {expected_type} doesn't match {(type(runtime2))}"

        exec.node_configs[0].append(node)
        runtime3: Runtime = Runtime(run_cond, exec)
        with self.assertRaises(AssertionError):
            runtime3.initialize()

        exec.node_configs.append(NodeConfig([node]))
        runtime4: Runtime = Runtime(run_cond, exec)
        with self.assertRaises(AssertionError):
            runtime4.initialize()


if __name__ == "__main__":
    unittest.main()
