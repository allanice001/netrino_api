from __future__ import absolute_import
from __future__ import unicode_literals

import nfw


class NetworkDeviceFields(object):

    class Meta(object):
        db_table = 'device'

    ip = nfw.Model.Integer()
    snmp_comm = nfw.Model.Text()
    name = nfw.Model.Text()
    vendor = nfw.Model.Text()
    os = nfw.Model.Text()
    os_ver = nfw.Model.Text()
    last_discover = nfw.Model.Datetime()


class NetworkDevices(NetworkDeviceFields, nfw.Model):
    pass


class NetworkDevice(NetworkDeviceFields, nfw.ModelDict):
    pass


class NetworkDevicePortFields(object):

    class Meta(object):
        db_table = 'device_port'

    id = nfw.Model.Integer()
    port = nfw.Model.Text()
    alias = nfw.Model.Text()
    prefix_len = nfw.Model.Integer()
    descr = nfw.Model.Text()
    name = nfw.Model.Text()
    mac = nfw.Model.Text()
    vlan = nfw.Model.Text()
    present = nfw.Model.Bool()
    igroup = nfw.Model.Uuid()


class NetworkDevicePorts(NetworkDevicePortFields, nfw.Model):
    pass


class NetworkDevicePort(NetworkDevicePortFields, nfw.ModelDict):
    pass


class NetworkServiceFields(object):

    class Meta(object):
        db_table = 'services'

    id = nfw.Model.Uuid(hidden=True)
    name = nfw.Model.Text(label="Service Name", required=True)
    interface_group = nfw.Model.Uuid()
    user_role = nfw.Model.Uuid()
    config_snippet = nfw.Model.Text(
        label="Configuration Snippet", required=True)
    fields = nfw.Model.Text()
    activate_snippet = nfw.Model.Text(
        label="Activation Snippet", required=True)
    deactivate_snippet = nfw.Model.Text(
        label="Deactivation Snippet", required=True)


class NetworkServices(NetworkServiceFields, nfw.Model):
    pass


class NetworkService(NetworkServiceFields, nfw.ModelDict):
    pass


class IGroupFields(object):

    class Meta(object):
        db_table = 'interface_groups'

    id = nfw.Model.Uuid(hidden=True)
    name = nfw.Model.Text(label="Interface Group", required=True)


class IGroups(IGroupFields, nfw.Model):
    pass


class IGroup(IGroupFields, nfw.ModelDict):
    pass

# class NetworkServiceRequestFields(object):

#     class Meta(object):
#         db_table = 'service_requests'

#     id = nfw.Model.Uuid()
#     device = nfw.Model.Integer(required=True)
#     port = nfw.Model.Text()
#     customer = nfw.Model.Uuid()
#     service = nfw.Model.Uuid()
#     resources = nfw.Model.Text()
#     result = nfw.Model.Text()
#     status = nfw.Model.Text()
#     creation_date = nfw.Model.Datetime()
#     task_id = nfw.Model.Uuid()


# class NetworkServiceRequests(NetworkServiceRequestFields, nfw.Model):
#     pass


# class NetworkServiceRequest(NetworkServiceRequestFields, nfw.ModelDict):
#     pass
