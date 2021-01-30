import numpy as np
import autograd.numpy as anp

from random import randint
from pymoo.algorithms.genetic_algorithm import GeneticAlgorithm
from pymoo.algorithms.ctaea import CTAEA as CTAEA_
from pymoo.algorithms.nsga3 import NSGA3 as NSGA3_
from pymoo.algorithms.nsga2 import NSGA2 as NSGA2_
from pymoo.factory import get_reference_directions
from pymoo.optimize import minimize
from abc import abstractmethod
from pymoo.model.problem import Problem
from typing import Dict, List
from edge import Edge
from dependencies import loadDependencies, Task, Application
from copy import deepcopy
from collections import defaultdict
from pprint import pformat
from pymoo.configuration import Configuration
from resourcesInfo import ResourcesInfo

Configuration.show_compile_hint = False
EdgesByName = Dict[str, List[str]]
MachinesByName = Dict[str, List[str]]


class Decision:

    def __init__(
            self,
            machines: Dict[str, str],
            edgeCost: float,
            computingCost: float,
    ):
        self.machines: Dict[str, str] = machines
        self.edgeCost: float = edgeCost
        self.computingCost: float = computingCost

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return pformat(
            object=self.__dict__,
            indent=3)


class Scheduler:

    def __init__(
            self,
            name: str,
            edges: Dict[str, Edge],
            averageProcessTime: Dict[str, float]):
        self.name: str = name
        self.edges: Dict[str, Edge] = edges
        self.averageProcessTime: Dict[str, float] = averageProcessTime
        tasksAndApps = loadDependencies()
        self.tasks: Dict[str, Task] = tasksAndApps[0]
        self.applications: Dict[str, Application] = tasksAndApps[1]

    def schedule(
            self,
            applicationName: str,
            label: str,
            userMachineID: str,
            availableWorkers: Dict[str, str],
            workersResources: Dict[str, ResourcesInfo]
    ) -> Decision:
        edgesByName = self.__getExecutionMap(
            applicationName,
            label=label)
        machinesByName = self.__getMachinesByName(
            applicationName=applicationName,
            label=label,
            userMachineID=userMachineID)
        return self._schedule(
            edgesByName,
            machinesByName,
            availableWorkers,
            workersResources)

    @abstractmethod
    def _schedule(
            self,
            edgesByName: EdgesByName,
            machinesByName: MachinesByName,
            availableWorkers: Dict[str, str],
            workersResources: Dict[str, ResourcesInfo]) -> Decision:
        raise NotImplementedError

    def __getExecutionMap(
            self,
            applicationName: str,
            label: str) -> EdgesByName:
        app = self.applications[applicationName]

        skipRoles = {'RemoteLogger'}
        replaceRoles = {'Sensor', 'Actor'}
        edgesByName = defaultdict(lambda: set([]))
        for taskName, dependency in app.dependencies.items():
            if taskName in skipRoles:
                continue
            if taskName in replaceRoles:
                taskName = 'Master'
            else:
                taskName = '%s@%s@TaskHandler' % (taskName, label)

            childTaskList = deepcopy(dependency.childTaskList)
            if 'Sensor' in childTaskList and 'Master' not in childTaskList:
                childTaskList.remove('Sensor')
                childTaskList.append('Master')
            if 'Actor' in childTaskList and 'Master' not in childTaskList:
                childTaskList.remove('Actor')
                childTaskList.append('Master')
            if 'RemoteLogger' in childTaskList:
                childTaskList.remove('RemoteLogger')
            for i, name in enumerate(childTaskList):
                if not name == 'Master':
                    childTaskList[i] = '%s@%s@TaskHandler' % (childTaskList[i], label)
                elif name == 'User':
                    childTaskList[i] = '%s@%s' % (applicationName, name)
            edgesByName[taskName].update(set(childTaskList))
        userAppName = '%s@%s@User' % (applicationName, label)
        edgesByName['Master'].update({userAppName})
        edgesByName[userAppName] = {'Master'}

        res = defaultdict(lambda: set([]))
        result = {}
        for k, v in edgesByName.items():
            for name in v:
                res[k].update([name])
            result[k] = list(res[k])
        return result

    def __getMachinesByName(
            self,
            applicationName: str,
            label: str,
            userMachineID: str) -> MachinesByName:
        userName = '%s@%s@User' % (applicationName, label)
        res = defaultdict(lambda: set([]))
        skipNames = {'RemoteLogger', 'Worker'}
        for edge in self.edges.values():
            source = edge.source.split('#')
            name = source[-2]
            if name in skipNames:
                continue
            machineID = source[-1]
            if name == userName:
                if not machineID == userMachineID:
                    continue
            res[name].update([machineID])
        result = {}
        for k, v in res.items():
            result[k] = list(v)
        return result


class Evaluator:

    def __init__(
            self,
            edges: Dict[str, Edge],
            averageProcessTime: Dict[str, float],
            edgesByName: EdgesByName,
            machinesByName: MachinesByName,
            workersResources: Dict[str, ResourcesInfo]):
        self.edges: Dict[str, Edge] = edges
        self.averageProcessTime: Dict[str, float] = averageProcessTime
        self.edgesByName = edgesByName
        self.machinesByName = machinesByName
        self.workersResources = workersResources

    def _edgeCost(self, individual: Dict[str, str]) -> float:
        total = .0
        for source, destinations in self.edgesByName.items():
            sourceName = '%s#%s' % (source, individual[source])
            for dest in destinations:
                destName = '%s#%s' % (dest, individual[dest])
                costKey = '%s,%s' % (sourceName, destName)
                if costKey in self.edges \
                        and self.edges[costKey].averageReceivedPackageSize is None:
                    total += self.edges[costKey].averageReceivedPackageSize
                    total += self.edges[costKey].delay
                    continue
                total += self.evaluateEdgeCost(source, individual[source], dest, individual[dest])

        # suppose bandwidth for all nodes are the same
        # and is 0.1 mb/ ms
        return total / (1024 ** 2 / 10)

    def evaluateEdgeCost(self, sourceName, sourceMachine, destName, destMachine):
        allReceivedStat = set([])
        averageReceivedStat = set([])
        for _, edge in self.edges.items():
            if edge.averageReceivedPackageSize is None:
                continue
            averageReceivedStat.add(edge.averageReceivedPackageSize)
            if sourceName != edge.source[len(sourceName)]:
                continue
            if destName != edge.destination[len(destName)]:
                continue
            averageReceivedStat.add(edge.averageReceivedPackageSize)

        if len(averageReceivedStat):
            averageReceivedPackageSize = sorted(averageReceivedStat)[len(averageReceivedStat) // 2]
        elif len(allReceivedStat):
            averageReceivedPackageSize = sorted(allReceivedStat)[len(allReceivedStat) // 2]
        else:
            averageReceivedPackageSize = 4096

        allDelayStat = set([])
        delayStat = set([])
        for _, edge in self.edges.items():
            if edge.delay is None:
                continue
            allDelayStat.add(edge.delay)
            if sourceMachine != edge.source[-len(sourceMachine):]:
                continue
            if destMachine != edge.destination[-len(destMachine):]:
                continue
            delayStat.add(edge.delay)

        if len(delayStat):
            delay = sorted(delayStat)[len(delayStat) // 2]
        elif len(allDelayStat):
            delay = sorted(allDelayStat)[len(allDelayStat) // 2]
        else:
            delay = 42

        return averageReceivedPackageSize + delay

    def _computingCost(self, individual: Dict[str, str]) -> float:
        total = .0
        for machineName in self.edgesByName.keys():
            if not machineName[-11:] == 'TaskHandler':
                continue
            taskHandlerName = '%s#%s' % (machineName, individual[machineName])
            if taskHandlerName in self.averageProcessTime \
                    and self.averageProcessTime[taskHandlerName] is None:
                total += self.averageProcessTime[taskHandlerName] * self.considerRecentResources(machineName)
                continue
            total += self.evaluateComputingCost(taskHandlerName) * self.considerRecentResources(machineName)
        return total

    def considerRecentResources(self, machineName):
        if machineName not in self.workersResources:
            return 1
        resources = self.workersResources[machineName]

        factor = 0
        factor += resources.totalSwapMemory / resources.availableSwapMemory
        factor += resources.totalMemory / resources.availableMemory
        factor += resources.currentTotalCPUUsage / 100

        return factor

    def evaluateComputingCost(self, taskHandlerName: str):
        taskName, machine = taskHandlerName.split('#')
        machineResources = self.workersResources[machine]
        maxProcessTime = 0
        for taskHandlerRecord, processTime in self.averageProcessTime.items():
            if processTime is None:
                continue
            if processTime > maxProcessTime:
                maxProcessTime = processTime
            taskNameRecord, machineRecord = taskHandlerRecord.split('#')
            if machineRecord not in self.workersResources:
                continue
            recordResources = self.workersResources[machineRecord]
            if taskNameRecord == taskName:
                return processTime * recordResources.currentCPUFrequency / machineResources.currentCPUFrequency
        return maxProcessTime


class BaseProblem(Problem, Evaluator):

    def __init__(
            self,
            edges: Dict[str, Edge],
            averageProcessTime: Dict[str, float],
            edgesByName: EdgesByName,
            machinesByName: MachinesByName,
            availableWorkers: Dict[str, str],
            workersResources: Dict[str, ResourcesInfo]):
        Evaluator.__init__(
            self,
            edges=edges,
            averageProcessTime=averageProcessTime,
            edgesByName=edgesByName,
            machinesByName=machinesByName,
            workersResources=workersResources)
        self.variableNumber = len(edgesByName)
        self.availableWorkers = availableWorkers
        choicesEachVariable = []
        for name in edgesByName.keys():
            if name.split('@')[-1] == 'TaskHandler':
                choicesEachVariable.append(len(availableWorkers[name.split('@')[0]]))
                continue
            if name in machinesByName:
                choicesEachVariable.append(len(machinesByName[name]))
                continue
            choicesEachVariable.append(1)

        lowerBound = [0 for _ in range(self.variableNumber)]
        upperBound = choicesEachVariable
        Problem.__init__(
            self,
            xl=lowerBound,
            xu=upperBound,
            n_obj=2,
            n_var=self.variableNumber,
            type_var=np.int,
            elementwise_evaluation=True)

    def _evaluate(self, x, out, *args, **kwargs):
        x = x.astype(int)
        individual = self.indexesToMachines(x)

        edgeCost = self._edgeCost(individual)
        computingCost = self._computingCost(individual)

        out['F'] = anp.column_stack([edgeCost, computingCost])

    def indexesToMachines(self, indexes: List[int]):
        res = {}
        keys = list(self.edgesByName.keys())
        for keysIndex, index in enumerate(indexes):
            key = keys[keysIndex]
            if key.split('@')[-1] == 'TaskHandler':
                res[key] = self.availableWorkers[key][index]
                continue
            if key in self.machinesByName:
                res[key] = self.machinesByName[key][index]
                continue
            res[key] = None
        return res


class NSGABase(Scheduler):
    def __init__(
            self,
            name: str,
            algorithm: GeneticAlgorithm,
            edges: Dict[str, Edge],
            averageProcessTime: Dict[str, float],
            generationNum: int,
    ):
        self.__generationNum: int = generationNum
        super().__init__(
            name=name,
            edges=edges,
            averageProcessTime=averageProcessTime)
        self.__algorithm = algorithm

    def _schedule(
            self,
            edgesByName: EdgesByName,
            machinesByName: MachinesByName,
            availableWorkers: Dict[str, str],
            workersResources: Dict[str, ResourcesInfo]) -> Decision:
        problem = BaseProblem(
            edges=self.edges,
            averageProcessTime=self.averageProcessTime,
            edgesByName=edgesByName,
            machinesByName=machinesByName,
            availableWorkers=availableWorkers,
            workersResources=workersResources)
        res = minimize(problem,
                       self.__algorithm,
                       seed=randint(0, 100),
                       termination=(
                           'n_gen',
                           self.__generationNum))
        machines = problem.indexesToMachines(list(res.X[0].astype(int)))
        edgeCost = res.F[0][0]
        computingCost = res.F[0][1]
        decision = Decision(
            machines=machines,
            edgeCost=edgeCost,
            computingCost=computingCost)
        return decision


class NSGA2(NSGABase):

    def __init__(self,
                 populationSize: int,
                 generationNum: int,
                 edges: Dict[str, Edge],
                 averageProcessTime: Dict[str, float]):
        super().__init__(
            'NSGA2',
            NSGA2_(
                pop_size=populationSize,
                eliminate_duplicates=True),
            edges,
            averageProcessTime,
            generationNum=generationNum)


class NSGA3(NSGABase):

    def __init__(self,
                 populationSize: int,
                 generationNum: int,
                 dasDennisP: int,
                 edges: Dict[str, Edge],
                 averageProcessTime: Dict[str, float]):
        refDirs = get_reference_directions(
            "das-dennis",
            2,
            n_partitions=dasDennisP)
        super().__init__(
            'NSGA3',
            NSGA3_(
                pop_size=populationSize,
                ref_dirs=refDirs,
                eliminate_duplicates=True),
            edges,
            averageProcessTime,
            generationNum=generationNum)


class CTAEA(NSGABase):

    def __init__(self,
                 generationNum: int,
                 dasDennisP: int,
                 edges: Dict[str, Edge],
                 averageProcessTime: Dict[str, float]):
        refDirs = get_reference_directions(
            "das-dennis",
            2,
            n_partitions=dasDennisP)
        super().__init__(
            'CTAEA',
            CTAEA_(
                ref_dirs=refDirs,
                seed=randint(0, 100)),
            edges,
            averageProcessTime,
            generationNum=generationNum)


if __name__ == '__main__':
    pass
