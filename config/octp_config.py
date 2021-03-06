# coding=utf-8
import logging
import etcd
import gevent

from octopus import constant
from octopus import err
from octopus.proto import config_proto
from octopus.util.stoppable import Stoppable

log = logging.getLogger(constant.LOGGER_NAME)


class OctpConfig(Stoppable):
    def __init__(self, etcd_options, service_name, handler):
        """

        :param etcd_options:
        :param service_name:
        :type etcd_options: dict
        :type service_name: str
        :return:
        """

        super(OctpConfig, self).__init__()

        self.etcd_options = etcd_options
        self.service_name = service_name
        self.handler = handler

        self.ec = etcd.Client(**etcd_options)

    def _start_handler(self):
        self._load()
        self._watcher_coroutine = gevent.spawn(self._start_wather)
        log.info('OctpConfig(%s) started', self.service_name)

    def _stop_handler(self):
        gevent.joinall([self._watcher_coroutine,])
        log.info('OctpConfig(%s) stopped', self.service_name)

    @property
    def handler(self):
        return self._handler

    @handler.setter
    def handler(self, new_handler):
        if not callable(new_handler):
            raise err.OctpProgramError('config handler MUST be callable!')

        self._handler = new_handler

    def _load(self):
        try:
            result = config_proto.get(self.ec, self.service_name)
        except err.OctpConfigNotFoundError:
            log.warn('Now, NO node for config(%s).', self.service_name)
            raise

        self._deal_watch_result(result)

    def _start_wather(self):
        return gevent.spawn(self._watcher_handler)

    def _watcher_handler(self):
        while not self._stop:
            try:
                result = config_proto.watch(self.ec, self.service_name, timeout=10)
                self._deal_watch_result(result)
            except etcd.EtcdWatchTimedOut:
                log.debug('config watch timeout')
                continue

    def _deal_watch_result(self, result):
        """

        :param result: watch 返回的EtcdResult对象
        :type result: etcd.EtcdResult
        :return:
        """

        log.debug('config change: %s', result)
        action = constant.CONFIG_ACTION.NONE

        if result.action in ('create', ):
            action = constant.CONFIG_ACTION.ADD
        elif result.action in ('delete', 'compareAndDelete'):
            action = constant.CONFIG_ACTION.DEL
        elif result.action in ('set', 'compareAndSwap', 'update'):
            action = constant.CONFIG_ACTION.UPDATE
        else:
            raise err.OctpConfigInvalidState('Encounter invalid action: %s', action)

        self._handler(result.value, action)