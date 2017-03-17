from __future__ import print_function
from collections import OrderedDict
from pyipcalc import *
from workers.tasks import *
from netrino_celery import app
from tachyon.api import api
from jinja2 import Template
import nfw
import sys
import datetime
import uuid
import re
import thread
import json


def getLoggedInUser(req):
    token = req.headers.get('X-Auth-Token', None)
    if token:
        db = nfw.Mysql()
        sql = ('SELECT user_id,user.username ' +
               'FROM token LEFT JOIN user ON ' +
               'user_id=user.id WHERE token=%s')
        result = db.execute(sql, (token,))
        if result:
            user_id = result[0]['user_id']
            username = result[0]['username']
            return {'user_id': user_id,
                    'username': username}


def addService(values, service_id):
    db = nfw.Mysql()
    serviceName = values.get('service_name', '')
    interfaceGroup = values.get('interface_group', '')
    userRole = values.get('user_role', '')
    snippet = values.get('config_snippet', '')
    activate_snippet = values.get('activate_snippet', None)
    deactivate_snippet = values.get('deactivate_snippet', None)
    fields = re.findall('{{ ?(.*?) ?}}', snippet)
    if activate_snippet:
        afields = re.findall('{{ ?(.*?) ?}}', activate_snippet)
    else:
        afields = None
    if deactivate_snippet:
        dfields = re.findall('{{ ?(.*?) ?}}', deactivate_snippet)
    else:
        dfields = None
    if not fields:
        fields = []
    if afields:
        fields.extend(afields)
    if dfields:
        fields.extend(dfields)
    if fields:
        fields = ','.join(list(set(fields)))
    else:
        fields = None
    values = [serviceName, interfaceGroup, userRole,
              snippet, activate_snippet, deactivate_snippet, fields]
    if service_id:
        sql = ("UPDATE services" +
               " SET name=%s," +
               " interface_group=%s," +
               " user_role=%s," +
               " config_snippet=%s," +
               " activate_snippet=%s," +
               " deactivate_snippet=%s," +
               " fields=%s" +
               " WHERE id=%s")
        values.append(service_id)
    else:
        values.append(uuid.uuid4())
        sql = ("INSERT INTO services" +
               " (name,interface_group,user_role,config_snippet," +
               " activate_snippet,deactivate_snippet,fields,id)" +
               " VALUES (%s,%s, %s, %s, %s, %s, %s, %s)")
    db.execute(sql, values)
    db.commit()


def iptoint(ip):
    iparr = ip.split('.')
    iparr.reverse()
    intip = 0
    for i in range(4):
        intip += int(iparr[i]) << i * 8
    return(intip)


def inttoip(intip):
    parts = []
    for i in range(4):
        parts.append(str(intip % 2 ** 8))
        intip >>= 8
    parts.reverse()
    return ".".join(parts)


def masktoprefix(mask):
    mask = iptoint(mask)
    return(str(bin(mask)).count('1'))


def readablemac(mac):
    parts = []
    for i in range(0, 6, 2):
        part = "{0:0{1}x}".format(
            ord(mac[i]), 2) + "{0:0{1}x}".format(ord(mac[i + 1]), 2)
        parts.append(part)
    return ":".join(parts)


def dlog(msg):
    f = open('/tmp/mylog', 'a')
    if isinstance(msg, str):
        f.write(msg + '\n')
    elif isinstance(msg, list) or isinstance(msg, tuple):
        f.write(str(msg))
    else:
        f.write(str(dir(msg)) + '\n')
    f.close()


def viewDevicePorts(req, resp, ip, view=None):
    if view == "select2":
        vals = []
        sql = 'SELECT * FROM interface where id=%s'
        vals.append(int(ip))
        db = nfw.Mysql()

        results = db.execute(sql, vals)

        if len(results) == 0:
            raise HTTPNotFound("Not Found", "Device/ports not found")
        ports = []
        for result in results:
            ports.append({'id': result['port'], 'text': result['name']})
        return json.dumps(ports, indent=4)
    else:
        rmap = {}
        rmap['interface_groups.name'] = 'igroupname'
        rmap['tenant.name'] = 'customername'
        rmap['services.name'] = 'service'
        ljo = OrderedDict()
        left_join = api.LeftJoin(rmap, ljo)
        ljo['(select max(id) as srid,device,port from service_requests group by device,port) srport'] = {'device_port.port': 'srport.port',
                                                                                                         'device_port.id': 'srport.device'}
        ljo['(select id,customer,service FROM service_requests WHERE status in ("SUCCESS","ACTIVE") ) srrest'] = {
            'srrest.id': 'srid'}
        ljo['tenant'] = {'srrest.customer': 'tenant.id'}
        ljo['interface_groups'] = {'device_port.igroup': 'interface_groups.id'}
        ljo['services'] = {'srrest.service': 'services.id'}
        where = "device_port.id"
        where_values = [ip]
        return api.sql_get('device_port', req, resp,
                           None, where=where, where_values=where_values,
                           left_join=left_join)


def discoverDevice(req, id=None):
    if id:
        id = int(id)
        db = nfw.Mysql()
        sql = 'SELECT snmp_comm FROM device where id=%s'
        result = db.execute(sql, (id,))
        if result:
            community = result[0]['snmp_comm']
        else:
            raise nfw.HTTPError(nfw.HTTP_404, "Device not found",
                                "POST don't PUT")
    else:
        rvalues = json.loads(req.read())
        if not 'snmp_comm' in rvalues:
            raise nfw.HTTPError(nfw.HTTP_404, "Missing required paramater",
                                "Required paramater 'snmp_comm' not found")
        elif not 'id' in rvalues:
            raise nfw.HTTPError(nfw.HTTP_404, "Missing required paramater",
                                "Required paramater 'id' not found")
        else:
            try:
                id = int(rvalues['id'])
            except:
                raise nfw.HTTPError(nfw.HTTP_404, 'Invalid type',
                                    "'id' must be integer")
            if deviceExists(id):
                raise nfw.HTTPError(nfw.HTTP_404, 'Device already exists',
                                    "PUT don't POST")
            community = rvalues['snmp_comm']

    try:
        ip = dec2ip(id, 4)
    except:
        raise nfw.HTTPError(nfw.HTTP_404, 'Invalid type',
                            "'id' is not a valid ip address")
    srid = addSR(device=id, snippet="Running discovery on " + ip)
    loggedInUser = getLoggedInUser(req)
    user = loggedInUser['username']
    task = addDevice.delay(host=ip, user=user, srid=srid, community=community)
    if task:
        addSR(taskID=task.task_id, srid=srid)
        return {'Service Request': {'id': str(srid), 'task id': str(task.task_id)}}
    else:
        raise nfw.HTTPError(nfw.HTTP_404, 'Failed to create service request',
                            "Failed to create service request")


# Mysql Left Join query.
# Calling mysqLJ(s,f,ljo,w,g) results in
# SELECT s1k AS s1v,s2k AS s2v FROM f LEFT JOIN lj ON o1k=o1v AND o2k=o2v WHERE w1k=w1v AND w2k=w2v GROUP BY g1,g2
# where
# s = dict {s1k:s1v,s2k:s2v}
# f = string
# ljo = OrderedDict with dicts: { lj:{o1k:o1v,o2k:o2v}, ... }
# w = dict {w1k:w1v,w2k:w2v}
# g = list (g1,g2,...)
#
# if sxk ends in .*, sxv is ignored
# returns list of dicts:
#  [{s1v:result[0][s1v],{s2v:result[0][s2v]} , {s1v:result[1][s1v],{s2v:result[1][s2v]}]
#

def mysqlLJ(s, f, ljo, w=None, g=None):
    sql = ['SELECT']
    vals = []
    for i, k in enumerate(s):
        if i > 0:
            sql.append(',')
        sql.append(k)
        if not re.search('\.\*$', k):
            sql.append('AS')
            sql.append(s[k])
    sql.append('FROM')
    sql.append(f)
    for k in ljo:
        sql.append('LEFT JOIN')
        sql.append(k)
        sql.append('ON')
        for i, o in enumerate(ljo[k]):
            if i > 0:
                sql.append('AND')
            sql.append(o + "=" + ljo[k][o])
    if w:
        sql.append('WHERE')
        for i, k in enumerate(w):
            if i > 0:
                sql.append('AND')
            if w[k]:
                sql.append(k + '=%s')
                vals.append(w[k])
            else:
                sql.append(k + " IS NULL")
    if g:
        sql.append('GROUP BY')
        for i, a in enumerate(g):
            if i > 0:
                sql.append(',')
            sql.append(g[i])
    db = nfw.Mysql()
    results = db.execute(' '.join(sql), vals)
    resources = []
    for result in results:
        res = {}
        for k in result:
            if result[k]:
                res[k] = result[k]
            else:
                res[k] = None
        resources.append(res)
    return resources


def getServices(req,resp,sid=None):
    db = nfw.Mysql()
    if sid:
        w = {'services.id': sid}
    else:
        w = {}
    rmap = {'services.*': ''}
    rmap['interface_groups.name'] = 'igroupname'
    ljo = OrderedDict()
    ljo['interface_groups'] = {
        'services.interface_group': 'interface_groups.id'}
    left_join = api.LeftJoin(rmap, ljo)
    results = api.sql_get_query(
        'services', req, resp, None, where=w.keys(),
        where_values=w.values(), left_join=left_join)
    services = []
    for result in results:
        services.append({'id': result['id'],
                         'name': result['name'],
                         'interface_group': result['igroupname'],
                         'igroup': result['interface_group'],
                         'user_role': result['user_role'],
                         'snippet': result['config_snippet'],
                         'activate': result['activate_snippet'],
                         'deactivate': result['deactivate_snippet'],
                         'fields': result['fields']})
    return services


def getCustServices(cid):
    db = nfw.Mysql()
    rmap = {'service_requests.port': 'port'}
    rmap['service_requests.creation_date'] = 'date'
    rmap['service_requests.status'] = 'status'
    rmap['service_requests.result'] = 'result'
    rmap['services.name'] = 'name'
    rmap['device.name'] = 'device'
    ljo = OrderedDict()
    ljo['services'] = {'service_requests.service': 'services.id'}
    ljo['device'] = {'service_requests.device': 'device.ip'}
    result = mysqlLJ(rmap, 'service_requests', ljo, {
                     'service_requests.customer': cid})
    nresults = len(result)
    services = []
    if nresults > 0:
        for i in range(nresults):
            services.append({'name': result[i]['name'],
                             'device': result[i]['device'],
                             'port': result[i]['port'],
                             'status': result[i]['status'],
                             'result': result[i]['result'],
                             'date': result[i]['date']})
    return services


def updateSR(srid, status):
    db = nfw.Mysql()
    if srid:
        sql = 'UPDATE service_requests SET status=%s WHERE id=%s'
        vals = (status, srid)
        db.execute(sql, vals)
        db.commit()


def getResources(resource, ip=None, igid=None, onlyActive=False):
    if resource == 'interfaces':
        rs = 'device_port'
        r = 'port'
        rmap = {rs + "." + r: r}
        ljo = OrderedDict()
        w = {'present': 1}
        if onlyActive:
            ljo['(select max(creation_date) as srid,device,port from service_requests group by device,port) srport'] = {'device_port.port': 'srport.port',
                                                                                                                        'device_port.ip': 'srport.device'}
            ljo['(select creation_date as id,customer,service FROM service_requests WHERE status in ("SUCCESS","ACTIVE") ) srrest'] = {
                'srrest.id': 'srid'}
            w['srrest.id'] = None
        else:
            ljo['(select "1") as srport'] = {'srport.1': '"1"'}
        if ip:
            w['device_port.ip'] = ip
        if igid:
            w['device_port.igroup'] = igid
    result = mysqlLJ(rmap, rs, ljo, w)
    resources = []
    nresults = len(result)
    if nresults > 0:
        for i in range(nresults):
            resources.append([result[i][r]])
        return resources
    else:
        return None


def getSnippet(serviceID):
    db = nfw.Mysql()
    snippet = []
    sql = '''SELECT config_snippet,activate_snippet,
		deactivate_snippet,fields from services where id=%s'''
    result = db.execute(sql, (serviceID,))
    nresults = len(result)
    if nresults > 0:
        snippet.append(result[0]['config_snippet'])
        snippet.append(result[0]['activate_snippet'])
        snippet.append(result[0]['deactivate_snippet'])
        fields = result[0]['fields'] or ''
        snippet.append(fields.split(','))
    return snippet


def addSR(device=None, taskID=None, srid=None, customer=None,
          port=None, service=None, snippet=None, resources=None):
    db = nfw.Mysql()
    if taskID and srid:
        sql = 'UPDATE service_requests set task_id=%s WHERE id=%s'
        vals = (taskID, srid)
    else:
        srid = str(uuid.uuid4())
        sql = ('INSERT INTO service_requests' +
               ' (id,device,customer,port,service,result,resources)' +
               ' VALUES (%s,%s,%s,%s,%s,%s,%s)')
        vals = (srid, device, customer, port, service, snippet, resources)
    db.execute(sql, vals)
    db.commit()
    return srid


def addCust(values, custid):
    name = values.get('customer_name')
    text_fields = OrderedDict()
    for field in sorted(values):
        text_fields[field] = values.get(field)
    fields = json.dumps(text_fields)
    db = nfw.Mysql()
    if custid:
        sql = 'UPDATE customers set name=%s,fields=%s WHERE id=%s'
        vals = (name, fields, custid)
    else:
        sql = 'INSERT INTO customers (id,name,fields) VALUES (%s,%s,%s)'
        vals = (uuid.uuid4(), name, fields)
    db.execute(sql, vals)
    db.commit()


def addIGroup(values, igid=None):
    igroup = values.get('interface_group')
    db = nfw.Mysql()
    if igid:
        sql = 'UPDATE interface_groups set name=%s WHERE id=%s'
        vals = (igroup, igid)
    else:
        igid = uuid.uuid4()
        sql = 'INSERT INTO interface_groups (id,name) VALUES (%s,%s)'
        vals = (igid, igroup)
    db.execute(sql, vals)
    db.commit()


def addSupernet(values, supernet, sid=None):
    supernet = values.get('supernet')
    db = nfw.Mysql()
    supernet = supernet.split('/')
    network = ip2dec(supernet[0], 4)
    prefix = int(supernet[1])
    vals = [network, prefix]
    if sid:
        sql = 'UPDATE supernets set network=%s,prefix=%s where id=%s'
        vals.append(sid)
    else:
        sql = 'INSERT INTO supernets (network,prefix,id) VALUES (%s,%s,%s)'
        vals.append(uuid.uuid4())
    db.execute(sql, vals)
    db.commit()


def removeCust(custid):
    db = nfw.Mysql()
    sql = 'DELETE FROM customers WHERE id=%s'
    db.execute(sql, (custid,))
    db.commit()


def removeIGroup(igid):
    db = nfw.Mysql()
    sql = 'DELETE FROM interface_groups WHERE id=%s'
    vals = (igid,)
    db.execute(sql, vals)
    db.commit()


def removeSupernet(sid):
    db = nfw.Mysql()
    sql = 'DELETE FROM supernets WHERE id=%s'
    vals = (sid,)
    db.execute(sql, vals)
    db.commit()


def removeService(sid):
    db = nfw.Mysql()
    sql = 'DELETE FROM services WHERE id=%s'
    vals = (sid,)
    db.execute(sql, vals)
    db.commit()


def removeDevice(did):
    try:
        db = nfw.Mysql()
        sql = 'DELETE FROM device WHERE ip=%s'
        vals = (did,)
        db.execute(sql, vals)
        db.commit()
        return json.dumps({'result': 'Success'})
    except:
        return json.dumps({'result': {'Failed': 'Failed to remove device %s' % id}})


def getCusts(custid=None, fields=None):
    vals = []
    if not custid:
        sql = "SELECT * FROM customers"
    else:
        sql = 'SELECT * FROM customers where id=%s'
        vals.append(custid)
    db = nfw.Mysql()
    results = db.execute(sql, vals)
    customers = {}
    for result in results:
        field_values = {'text': OrderedDict(), 'textarea': OrderedDict()}
        if result['fields'] and fields:
            field_results = json.loads(result['fields'])
            for t in fields['text']:
                field_values['text'][t] = field_results[
                    t] if t in field_results else ''
            for t in fields['textarea']:
                field_values['textarea'][t] = field_results[
                    t] if t in field_results else ''
        else:
            field_values = None
        customers[result['id']] = {"name": result['name'],
                                   "fields": field_values}
    return json.dumps(customers)


def getIGroups(igid=None, view=None):
    vals = []
    if not igid:
        sql = "SELECT * FROM interface_groups"
    else:
        sql = 'SELECT * FROM interface where id=%s'
        vals.append(igid)
    db = nfw.Mysql()

    results = db.execute(sql, vals)

    if view == "select2":
        igroups = []
        for result in results:
            igroups.append({'id': result['id'], 'text': result['name']})
    elif view == "datatable":
        igroups = []
        for result in results:
            igroups.append({'name': result['name'],
                            'id': result['id']})
    else:
        igroups = {}
        for result in results:
            igroups[result['id']] = result['name']

    return igroups


def getSupernets(sid=None):
    if not sid:
        sql = "SELECT * FROM supernets"
        vars = ()
    else:
        sql = 'SELECT * FROM supernets where id="%s"'
        vars = (sid,)
    db = nfw.Mysql()
    results = db.execute(sql, vars)
    supernets = {}
    for result in results:
        # perhaps the supernets table needs a version column
        supernets[result['id']] = str(dec2ip(result['network'], 4))
        supernets[result['id']] += "/" + str(result['prefix'])
    return supernets


def assignIGPort(req, id):
    values = json.loads(req.read())
    port = values['port']
    ip = values['device']
    db = nfw.Mysql()
    sql = 'UPDATE device_port set igroup=%s WHERE id=%s AND port=%s'
    result = db.execute(sql, (id, ip, port))
    db.commit()
    if result > 0:
        port_igroup = {'id': port,
                       'igroup': id,
                       'device': ip}
        return port_igroup
    else:
        raise nfw.HTTPError(nfw.HTTP_404, 'Port Interface group assignment failed',
                            'Item not found %s' % (str(result),))


rfc5735 = [IPNetwork('10.0.0.0/8')]
rfc5735.append(IPNetwork('172.16.0.0/12'))
rfc5735.append(IPNetwork('192.168.0.0/16'))
rfc5735.append(IPNetwork('127.0.0.0/8'))
rfc5735.append(IPNetwork('0.0.0.0/8'))
rfc5735.append(IPNetwork('127.0.0.0/8'))
rfc5735.append(IPNetwork('169.254.0.0/16'))
rfc5735.append(IPNetwork('192.0.0.0/24'))
rfc5735.append(IPNetwork('192.0.2.0/24'))
rfc5735.append(IPNetwork('192.88.99.0/24'))
rfc5735.append(IPNetwork('198.18.0.0/15'))
rfc5735.append(IPNetwork('198.51.100.0/24'))
rfc5735.append(IPNetwork('223.255.255.0/24'))
rfc5735.append(IPNetwork('203.0.113.0/24'))
rfc5735.append(IPNetwork('224.0.0.0/4'))
rfc5735.append(IPNetwork('240.0.0.0/4'))
rfc5735.append(IPNetwork('255.255.255.255/32'))


def isRFC5735(net):
    for i in rfc5735:
        if i.contains(net):
            return True
    return False


def updateSupernets(did):
    minpl = config.get('netrino').get('minimum_prefix_length')
    db = nfw.Mysql()
    sresults = db.execute('SELECT * FROM supernets')
    ipresults = db.execute('''SELECT alias,prefix_len 
			   FROM device_port WHERE alias
			   IS NOT NULL AND present=1 AND
			   ip=%s''', (did,))
    existing_supernets = {}
    new_supernets = []
    for sr in sresults:
        ipnet = IPNetwork(dec2ip(sr['network'], 4) + '/' + str(sr['prefix']))
        existing_supernets[sr['id']] = ipnet
    for ipresult in ipresults:
        ip = ipresult['alias']
        pl = ipresult['prefix_len']
        pl = pl if pl > 0 else 32
        iprefix = '/' + str(pl)
        ipnet = IPNetwork(ip + iprefix)
        if not isRFC5735(ipnet):
            dec_ip = ip2dec(ip, ipnet._version)
            if not existing_supernets:
                existing_supernets[1] = ipnet
            else:
                known = False
                for sid in existing_supernets:
                    if existing_supernets[sid].contains(ipnet):
                        known = True
                        break
                if not known:
                    for sid in existing_supernets:
                        biggersn = supernet(existing_supernets[
                                            sid], ipnet, minpl)
                        if biggersn:
                            existing_supernets[sid] = biggersn
                            break
                    if not biggersn:
                        new_supernets.append(ipnet)
    for sid in existing_supernets:
        sql = "UPDATE supernets SET network=%s,prefix=%s WHERE id=%s"
        s = existing_supernets[sid]
        network = ip2dec(s.ip_network, s._version)
        prefix = s._cidr
        db.execute(sql, (network, prefix, sid))
    for s in new_supernets:
        sql = 'INSERT INTO supernets (network,prefix) VALUES (%s,%s)'
        network = ip2dec(s.ip_network, s._version)
        prefix = s._cidr
        db.execute(sql, (network, prefix))
    db.commit()


def getSNMPComm(device_id):
    db = nfw.Mysql()
    results = db.execute(
        'SELECT snmp_comm FROM device WHERE ip = %s', (device_id,))
    if results:
        return results[0]['snmp_comm']
    else:
        return None


def getCustFields():
    configured_fields = config.get('customer_fields')
    if configured_fields:
        # removing all spaces, tabs, etc:
        text_fields = ''.join(configured_fields.get('text').split())
        textarea_fields = ''.join(configured_fields.get('textarea').split())
        fields = {}
        fields['text'] = OrderedDict()
        fields['text'] = sorted(text_fields.split(','))
        fields['textarea'] = OrderedDict()
        fields['textarea'] = sorted(textarea_fields.split(','))
        return fields
    else:
        return None


def checkResourceUsage(resource, rid):
    if resource == "igroup":
        sql = 'SELECT port FROM device_port WHERE igroup = %s'
    elif resource == "customer":
        sql = 'SELECT id FROM service_requests WHERE customer = %s AND status="ACTIVE"'
    db = nfw.Mysql()
    resources = db.execute(sql, (rid,))
    if resources:
        return json.dumps(len(resources))
    else:
        return json.dumps(0)


def deviceExists(id):
    db = nfw.Mysql()
    sql = 'SELECT count(id) as count FROM device where id=%s'
    result = db.execute(sql, (id,))
    if result[0]['count'] > 0:
        return True
    else:
        return False


def viewSR(req, resp, id=None, view=None, onlyActive=False):
    srs = []
    w = {}
    search = req.headers.get('X-Search-Specific', None)
    if search:
        search = search.split(',')
        for i in search:
            key, value = i.split('=')
            key = 'service_requests.' + key.strip()
            w[key] = value.strip()
    if id:
        w['service_requests.id'] = id
    if onlyActive:
        w['service_requests.status'] = 'ACTIVE'
    log.debug("MYDEBUG:\n%s\n%s" % (w.keys(), w.values()))
    rmap = {}
    rmap['tenant.name'] = 'customer_name'
    rmap['services.name'] = 'service_name'
    ljo = OrderedDict()
    ljo['tenant'] = {'service_requests.customer': 'tenant.id'}
    ljo['services'] = {'services.id': 'service_requests.service'}
    left_join = api.LeftJoin(rmap, ljo)
    results = api.sql_get_query(
        'service_requests', req, resp, None, where=w.keys(),
        where_values=w.values(), left_join=left_join)
    nresults = len(results)
    if nresults > 0:
        completed = ('FAILURE', 'SUCCESS', 'UNKNOWN', 'ACTIVE', 'INACTIVE')
        now = datetime.datetime.today()
        for result in results:
            srid = result['id']
            status = result['status']
            ctime = result['creation_date']
            timedelta = now - ctime
            if status not in completed:
                #app = getApp(req)
                res = app.AsyncResult(result['task_id'])
                if res.ready() or timedelta.seconds < 3600:
                    status = res.state
                else:
                    status = 'UNKNOWN'
                updateSR(srid=srid, status=status)
            device = result['device']
            device = dec2ip(int(device), 4)
            srs.append({'id': srid,
                        'creation_date': str(result['creation_date']),
                        'device': device,
                        'task_id': result['task_id'],
                        'customer': result['customer_name'],
                        'result': result['result'],
                        'service': result['service_name'],
                        'status': status})  # TODO User that created the SR
    # if len(srs) == 1:
    #     return srs[0]
    # else:
    return srs


def createSR(req):
    values = json.loads(req.read())
    deviceID = values['device']
    serviceID = values['service'] if 'service' in values else None
    customerID = values['customer'] if 'customer' in values else None
    port = values['interface'] if 'interface' in values else None
    snippet = getSnippet(serviceID)
    jsnip = Template(snippet[0])
    resources = {}
    for i in snippet[3]:
        try:
            resources[i] = values[i]
        except:
            raise nfw.HTTPError(nfw.HTTP_404, 'Service creation failed',
                                'Missing attribute: %s' % i)
    snippet = jsnip.render(**resources)
    db = nfw.Mysql()
    deviceIP = inttoip(deviceID)
    unit = re.search(r'interfaces.*{\n.*\n* +unit (.*) {', snippet)
    if port and unit:
        port += "." + unit.group(1)
    srid = addSR(device=deviceID, customer=customerID, port=port,
                 service=serviceID, snippet=snippet,
                 resources=json.dumps(resources))
    loggedInUser = getLoggedInUser(req)
    user = loggedInUser['username']
    task = confDevice.delay(deviceIP, user=user,
                            snippet=snippet, srid=srid)
    addSR(taskID=task.id, srid=srid)
    result = {"Service Request ID": srid,
              "Task ID": task.id}
    return result


def activateSR(req, srid):
    db = nfw.Mysql()
    sql = 'SELECT service,resources,device FROM service_requests WHERE id=%s'
    result = db.execute(sql, (srid,))
    if result:
        device = result[0]['device']
        sid = result[0]['service']
        resources = result[0]['resources']
        resources = json.loads(resources) if resources else None
        sql = 'SELECT activate_snippet FROM services WHERE id=%s'
        sresult = db.execute(sql, (sid,))
        if sresult[0]['activate_snippet']:
            ajsnip = Template(sresult[0]['activate_snippet'])
            activation_snippet = ajsnip.render(**resources)
            sql = ('UPDATE service_requests SET status="PENDING"' +
                   ' WHERE id=%s')
            db.execute(sql, (srid,))
            db.commit()
            deviceIP = dec2ip(int(device), 4)
            loggedInUser = getLoggedInUser(req)
            user = loggedInUser['username']
            task = confDevice.delay(deviceIP,
                                    user=user, snippet=activation_snippet,
                                    srid=srid, activate=True)
            addSR(taskID=task.task_id, srid=srid)
            return {"Service Request ID": srid,
                    "Task ID": task.id}
        else:
            sql = ('UPDATE service_requests SET status="ACTIVE"' +
                   ' WHERE id=%s')
            db.execute(sql, (srid,))
            db.commit()
            return {"Service Request ID": srid}
    else:
        raise nfw.HTTPError(nfw.HTTP_404, 'Service activation failed',
                            'Service request not found: %s' % (srid,))


def deactivateSR(req, srid):
    db = nfw.Mysql()
    sql = 'SELECT service,resources,device FROM service_requests WHERE id=%s'
    result = db.execute(sql, (srid,))
    if result:
        device = result[0]['device']
        sid = result[0]['service']
        resources = result[0]['resources']
        resources = json.loads(resources) if resources else None
        sql = 'SELECT deactivate_snippet FROM services WHERE id=%s'
        sresult = db.execute(sql, (sid,))
        if sresult[0]['deactivate_snippet']:
            djsnip = Template(sresult[0]['deactivate_snippet'])
            deactivation_snippet = djsnip.render(**resources)
            sql = ('UPDATE service_requests SET status="PENDING"' +
                   ' WHERE id=%s')
            db.execute(sql, (srid,))
            db.commit()
            deviceIP = dec2ip(int(device), 4)
            loggedInUser = getLoggedInUser(req)
            user = loggedInUser['username']
            task = confDevice.delay(deviceIP,
                                    user=user, snippet=deactivation_snippet,
                                    srid=srid, deactivate=True)
            addSR(taskID=task.task_id, srid=srid)
            return {"Service Request ID": srid,
                    "Task ID": task.id}
        else:
            sql = ('UPDATE service_requests SET status="INACTIVE"' +
                   ' WHERE id=%s')
            db.execute(sql, (srid,))
            db.commit()
            return {"Service Request ID": srid}
    else:
        raise nfw.HTTPError(nfw.HTTP_404, 'Service activation failed',
                            'Service request not found: %s' % (srid,))
