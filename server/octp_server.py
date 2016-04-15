# coding=utf-8
import etcd
import time
import logging
import gevent

import err
import constant
from proto import service_proto

log = logging.getLogger(constant.LOGGER_NAME)

class OctpServer():
    def __init__(self, etcd_options, service_name, service_addr):
        self.etcd_options = etcd_options
        self.service_name = service_name
        self.service_addr = service_addr

        self.ec = etcd.Client(**self.etcd_options)
        self._token = ''

    def init(self):
        """
        publish service into etcd.
        :return:
        :attention: Please ensure Listen completed BEFORE publish service into etcd.
        """

        # STEP 1: publish first.
        self._publish()

        gevent.spawn(self._start_watcher)  # 启动etcd服务监听器
        gevent.spawn(self._heartbeat)  # 启动心跳包

    def destroy(self):
        service_proto.unregister(self.ec, self._token)


    def _start_watcher(self):
        """
        监听etcd服务器的状态，当连接丢失时，尝试重连。
        :return:
        """

        while True:
            try:
                self.ec.watch(constant.ROOT_NODE, timeout=constant.WATCH_TIMEOUT)
            except etcd.EtcdWatchTimedOut:
                continue
            except etcd.EtcdConnectionFailed:
                # TODO 处理etcd服务器断开的情况
                log.warn('etcd can NOT connect, maybe crash')
                gevent.sleep(constant.ETCD_RECONNECT_INTERVAL)
            except Exception as e:
                log.warn('unexpected Error: %s', e)
                raise

    def _heartbeat(self):
        while True:
            log.debug('refresh ttl for %s', self.service_name)
            service_proto.alive(self.ec, self.service_name, self._token)
            time.sleep(constant.SERVICE_REFRESH_INTERVAL)

    def _publish(self):
        for retry in range(constant.ETCD_RECONNECT_MAX_RETRY_INIT):
            try:
                g = gevent.spawn(self._publish_handler)
                g.join(constant.ETCD_CONNECT_TIMEOUT)

                e = g.exception
                if e:
                    raise e
            except (etcd.EtcdConnectionFailed, gevent.Timeout):
                log.info('Connect to etcd failed, Retry(%d)...', retry)
                gevent.sleep(constant.ETCD_RECONNECT_INTERVAL)
            else:
                log.info('Publish OK.')
                break
        else:  # publish failed
            raise err.OctpEtcdConnectError('Max attempts exceeded.')

    def _publish_handler(self):
        try:
            self._token = service_proto.register(self.ec, self.service_name, self.service_addr)
        except etcd.EtcdConnectionFailed:
            log.warn('connect to etcd failed.')
            # TODO 完善处理流程
            raise
        else:
            log.info('publish service(%s: %s) to etcd SUCCESS.', self.service_name, self.service_addr)