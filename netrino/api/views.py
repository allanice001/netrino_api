
from __future__ import absolute_import, print_function
from __future__ import unicode_literals

import logging

import json
import sys

from netrino.api import model as modelapi
from tachyon.api import api
from .functions import *


import nfw

log = logging.getLogger(__name__)


@nfw.app.resources()
class ServiceRequests(object):

    def __init__(self, app):
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/service_requests', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/service_requests/{id}', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_POST, '/infrastructure/network/service_requests',
                       self.post, 'network:admin')
        app.router.add(
            nfw.HTTP_PUT, '/infrastructure/network/service_requests/{id}', self.put, 'network:admin')
        app.router.add(
            nfw.HTTP_DELETE, '/infrastructure/network/service_requests/{id}', self.delete, 'network:admin')

    def get(self, req, resp, id=None):
        view = req.post.get('view', None)
        onlyActive = req.post.get('onlyActive', False)
        result = viewSR(req, resp, id=id, view=view, onlyActive=onlyActive)
        return json.dumps(result, indent=4)

    def post(self, req, resp):
        result = createSR(req)
        return json.dumps(result, indent=4)

    def put(self, req, resp, id):
        result = activateSR(req, srid=id)
        return json.dumps(result, indent=4)

    def delete(self, req, resp, id):
        result = deactivateSR(req, srid=id)
        return json.dumps(result, indent=4)


@nfw.app.resources()
class NetworkDevice(object):

    def __init__(self, app):
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/devices', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/devices/{id}', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/devices/{id}/ports', self.ports,
                       'network:admin')
        app.router.add(nfw.HTTP_POST, '/infrastructure/network/devices', self.post,
                       'network:admin')
        app.router.add(
            nfw.HTTP_PUT, '/infrastructure/network/devices/{id}', self.put, 'network:admin')
        app.router.add(nfw.HTTP_DELETE, '/infrastructure/network/devices/{id}', self.delete,
                       'users:admin')

    def get(self, req, resp, id=None):
        return api.get(modelapi.NetworkDevices, req, resp, id)

    def ports(self, req, resp, id):
        view = req.post.get('view', None)
        return viewDevicePorts(req, resp, ip=int(id), view=view)

    def post(self, req, resp):
        result = discoverDevice(req)
        return json.dumps(result, indent=4)

    def put(self, req, resp, id=None):
        result = discoverDevice(req, id)
        return json.dumps(result, indent=4)

    def delete(self, req, resp, id=None):
        return api.delete(modelapi.NetworkDevice, req, id)


@nfw.app.resources()
class NetworkService(object):

    def __init__(self, app):
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/services', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/services/{id}', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_POST, '/infrastructure/network/services', self.post,
                       'network:admin')
        app.router.add(nfw.HTTP_PUT, '/infrastructure/network/services/{id}', self.put,
                       'network:admin')
        app.router.add(nfw.HTTP_DELETE, '/infrastructure/network/services/{id}', self.delete,
                       'network:admin')

    def get(self, req, resp, id=None):
        view = req.post.get('view', None)
        if view == "datatable":
            result = getServices(req,resp,sid=id)
            return json.dumps(result, indent=4)
        else:
            return api.get(modelapi.NetworkServices, req, resp, id)

    def post(self, req, resp):
        return api.post(modelapi.NetworkService, req)

    def put(self, req, resp, id):
        return api.put(modelapi.NetworkService, req, id)

    def delete(self, req, resp, id):
        return api.delete(modelapi.NetworkService, req, id)


@nfw.app.resources()
class InterfaceGroup(object):

    def __init__(self, app):
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/igroups', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_POST, '/infrastructure/network/igroups', self.post,
                       'network:admin')
        app.router.add(nfw.HTTP_GET, '/infrastructure/network/igroups/{id}', self.get,
                       'network:admin')
        app.router.add(nfw.HTTP_PUT, '/infrastructure/network/igroups/{id}', self.put,
                       'network:admin')
        app.router.add(nfw.HTTP_PUT, '/infrastructure/network/igroups/{id}/port',
                       self.portigroup, 'network:admin')
        app.router.add(nfw.HTTP_DELETE, '/infrastructure/network/igroups/{id}', self.delete,
                       'network:admin')

    def get(self, req, resp, id=None):
        view = req.post.get('view', None)
        if id or view == "datatable":
            # return api.get(modelapi.IGroups, req, resp, id)
            return api.sql_get("interface_groups", req, resp, id)
        else:
            return json.dumps(getIGroups(id, view), indent=4)

    def post(self, req, resp):
        return api.post(modelapi.IGroup, req)

    def put(self, req, resp, id):
        return api.put(modelapi.IGroup, req, id)

    def delete(self, req, resp, id):
        return api.delete(modelapi.IGroup, req, id)

    def portigroup(self, req, resp, id):
        result = assignIGPort(req, id)
        return json.dumps(result, indent=4)
