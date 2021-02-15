import logging
import threading
import docker
import os
import json
from logger import get_logger
from tqdm import tqdm
from typing import List
from time import sleep


class Experiment:

    def __init__(self):
        self.currPath = os.path.abspath(os.path.curdir)
        self.client = docker.from_env()
        self.logger = get_logger('Experiment', level_name=logging.DEBUG)

    def stopAllContainers(self):
        # os.system('docker stop $(docker ps -a -q) && docker rm $(docker ps -a -q)')
        try:
            containerList = self.client.containers.list()
        except Exception:
            self.stopAllContainers()
            return
        events: List[threading.Event] = [threading.Event() for _ in range(len(containerList))]
        for i, container in enumerate(containerList):
            self.stopContainer(container, events[i])
        # for event in tqdm(
        #         events,
        #         desc='Stopping Running Containers',
        #         unit='container'):
        #     event.wait()

    def stopContainer(self, container, event):
        threading.Thread(
            target=self.__stopContainer,
            args=(container, event)).start()

    @staticmethod
    def __stopContainer(container, event):
        # self.logger.info('[*] Stopping %s ...', container.name)
        try:
            container.stop()
        except Exception:
            pass
        # self.logger.info('[*] Stopped %s ...', container.name)
        event.set()

    def _run(self, **kwargs):
        return self.client._containers._runContainerStat(
            detach=True,
            auto_remove=True,
            network_mode='host',
            working_dir='/workplace',
            **kwargs)

    def runRemoteLogger(self):
        return self._run(
            name='RemoteLogger',
            image='remote-logger',
            volumes={
                '%s/newLogger/sources' % self.currPath: {
                    'bind': '/workplace',
                    'mode': 'rw'}
            },
            command='RemoteLogger '
                    '192.168.3.20 5001 '
                    '192.168.3.20 5000')

    def runMaster(self, schedulerName):
        return self._run(
            name='Master',
            image='master',
            volumes={
                '%s/newMaster/sources' % self.currPath: {
                    'bind': '/workplace',
                    'mode': 'rw'}
            },
            command='Master '
                    '192.168.3.20 5000 '
                    '192.168.3.20 5001 '
                    '%s' % schedulerName)

    def runWorker(
            self,
            name: str,
            core: str = None,
            cpuFreq: int = None,
            mem: str = None):
        return self._run(
            name=name,
            image='worker',
            volumes={
                '%s/newWorker/sources' % self.currPath: {
                    'bind': '/workplace',
                    'mode': 'rw'},
                '/var/run/docker.sock': {
                    'bind': '/var/run/docker.sock',
                    'mode': 'rw'}
            },
            command='Worker '
                    '192.168.3.20 '
                    '192.168.3.20 5000 '
                    '192.168.3.20 5001')

    def runUser(self, name):
        return self._run(
            name=name,
            image='user',
            volumes={
                '%s/newUser/sources' % self.currPath: {
                    'bind': '/workplace',
                    'mode': 'rw'}
            },
            command='User '
                    '192.168.3.20 '
                    '192.168.3.20 5000 '
                    '192.168.3.20 5001 '
                    'GameOfLifePyramid '
                    '256 '
                    '--no-show')

    @staticmethod
    def readRespondTime(filename):
        with open(filename) as f:
            respondTime = json.loads(f.read())
            f.close()
            os.system('rm -f %s' % filename)
            if len(respondTime):
                return list(respondTime.values())[0]
            return 0

    def removeLogs(self):
        os.system('rm -rf %s/newLogger/sources/profiler/*.json' % self.currPath)
        os.system('rm -rf %s/newMaster/sources/profiler/*.json' % self.currPath)

    @staticmethod
    def runRemoteWorkers():
        os.system('ssh 4GB-rpi-4B-alpha \'cd new/containers/newWorker '
                  '&& docker-compose run --rm --name Worker worker '
                  'Worker '
                  '192.168.3.49 '
                  '192.168.3.20 5000 '
                  '192.168.3.20 5001 > /dev/null 2>&1 &\'')
        os.system('ssh 2GB-rpi-4B-alpha \'cd new/containers/newWorker '
                  '&& docker-compose run --rm --name Worker worker '
                  'Worker '
                  '192.168.3.14 '
                  '192.168.3.20 5000 '
                  '192.168.3.20 5001 > /dev/null 2>&1 &\'')
        os.system('ssh 4GB-rpi-4B-beta \'cd new/containers/newWorker '
                  '&& docker-compose run --rm --name Worker worker '
                  'Worker '
                  '192.168.3.73 '
                  '192.168.3.20 5000 '
                  '192.168.3.20 5001 > /dev/null 2>&1 &\'')
        os.system('ssh 2GB-rpi-4B-beta \'cd new/containers/newWorker '
                  '&& docker-compose run --rm --name Worker worker '
                  'Worker '
                  '192.168.3.72 '
                  '192.168.3.20 5000 '
                  '192.168.3.20 5001 > /dev/null 2>&1 &\'')

    @staticmethod
    def stopRemoteWorkers():
        os.system('ssh 4GB-rpi-4B-alpha \''
                  'sudo service docker restart '
                  '&& docker rm $(docker ps -a -q)\' > /dev/null 2>&1')
        os.system('ssh 2GB-rpi-4B-alpha \''
                  'sudo service docker restart '
                  '&& docker rm $(docker ps -a -q)\' > /dev/null 2>&1')
        os.system('ssh 4GB-rpi-4B-beta \''
                  'sudo service docker restart '
                  '&& docker rm $(docker ps -a -q)\' > /dev/null 2>&1')
        os.system('ssh 2GB-rpi-4B-beta \''
                  'sudo service docker restart '
                  '&& docker rm $(docker ps -a -q)\' > /dev/null 2>&1')

    @staticmethod
    def stopLocalTaskHandler():
        os.system('docker stop $(docker ps -a -q --filter="name=TaskHandler") > /dev/null 2>&1')

    @staticmethod
    def stopRemoteTaskHandler():
        os.system('ssh 4GB-rpi-4B-alpha \''
                  'docker stop '
                  '$(docker ps -a -q '
                  '--filter="name=TaskHandler")\' > /dev/null 2>&1')
        os.system('ssh 2GB-rpi-4B-alpha \''
                  'docker stop '
                  '$(docker ps -a -q '
                  '--filter="name=TaskHandler")\' > /dev/null 2>&1')
        os.system('ssh 4GB-rpi-4B-beta \''
                  'docker stop '
                  '$(docker ps -a -q '
                  '--filter="name=TaskHandler")\' > /dev/null 2>&1')
        os.system('ssh 2GB-rpi-4B-beta \''
                  'docker stop '
                  '$(docker ps -a -q '
                  '--filter="name=TaskHandler")\' > /dev/null 2>&1')

    def rerunNecessaryContainers(self, schedulerName):
        self.stopAllContainers()
        self.stopRemoteWorkers()
        self.runRemoteLogger()
        self.runMaster(schedulerName)
        self.runWorker('Worker')
        self.runRemoteWorkers()

    def run(self, schedulerName, roundNum=None, targetRound=None):

        repeatTimes = 100
        userMaxWaitTime = 300
        respondTimeFilePath = '%s/newUser/sources/log/respondTime.json' % self.currPath
        respondTimes = [0 for _ in range(repeatTimes)]

        self.removeLogs()
        self.rerunNecessaryContainers(schedulerName)
        if roundNum is None:
            desc = schedulerName
        else:
            desc = '[%s-%d/%d]' % (schedulerName, roundNum, targetRound)

        i = 0
        processBar = tqdm(
            total=repeatTimes,
            desc=desc)
        while i < repeatTimes:
            user = self.runUser('User')
            # self.logger.debug('Waiting for respondTime log file to be created ...')
            sleepCount = 0
            while not os.path.exists(respondTimeFilePath):
                sleepCount += 1
                sleep(1)
                if sleepCount > userMaxWaitTime:
                    break
            try:
                user.stop()
            except docker.errors.NotFound:
                pass
            self.stopLocalTaskHandler()
            self.stopRemoteTaskHandler()
            if sleepCount > userMaxWaitTime:
                self.rerunNecessaryContainers(schedulerName)
                continue
            respondTimes[i] = self.readRespondTime(respondTimeFilePath)
            i += 1
            processBar.update(1)
            self.saveEvaluateRecord(schedulerName, roundNum, i)
            self.logger.debug('[*] Result-[%d/%d]: %s', (i + 1), repeatTimes, str(respondTimes))
        self.saveRes(schedulerName, respondTimes, roundNum)
        self.logger.info(respondTimes)

    @staticmethod
    def saveEvaluateRecord(algorithmName, roundNum, iterationNum):
        os.system('mv '
                  './newMaster/source/record.json '
                  './%s-%d-%d.json' % (algorithmName, roundNum, iterationNum))

    @staticmethod
    def saveRes(schedulerName, respondTimes, roundNum):
        if roundNum is None:
            filename = '%s.json' % schedulerName
        else:
            filename = '%s-%d.json' % (schedulerName, roundNum)
        with open(filename, 'w+') as f:
            json.dump(respondTimes, f)
            f.close()


if __name__ == '__main__':
    experiment = Experiment()
    targetRound_ = 10
    for num in range(targetRound_):
        experiment.run('NSGA3', num, targetRound_)
        experiment.run('NSGA2', num, targetRound_)
