#!/usr/bin/env python
#Copyright (c) 1999-2015, Juniper Networks Inc.
#               2016, Roslan Zaki
#
#
# All rights reserved.
#
# License: Apache 2.0
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
# * Neither the name of the Juniper Networks nor the
#   names of its contributors may be used to endorse or promote products
#   derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY Juniper Networks, Inc. ''AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL Juniper Networks, Inc. BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

DOCUMENTATION = '''
---
module: junos_jsnapy
author: Roslan Zaki, Juniper Networks
version_added: "1.0.0"
version_control:
    13-Apr-2016     v1.0.0      - Basic working model

Short_description: Integrate JSnapy to ansible
description:
    - Execute JSnapy module from Ansible
requirements:
    - junos-eznc >= 1.2.2
options:
    host:
        description:
            - Set to {{ inventory_hostname }}
        required: true
    user:
        description:
            - Login username
        required: false
        default: $USER
    passwd:
        description:
            - Login password
        required: false
        default: assumes ssh-key active
    port:
        description:
            - TCP port number to use when connecting to the device
        required: false
        default: 830
    logfile:
        description:
            - Path on the local server where the progress status is logged
              for debugging purposes
        required: false
        default: None
    dest:
        description:
            - Path to the local server directory where configuration will
              be saved.
        required: true
        default: None
    dir:
        description:
            - Path for the JSNAPy yaml configuration file
        required: false
        default: '/etc/jsnapy/testfiles'
    action:
        description:
            Possible actions available
            - jsnapcheck
            - check
            - snap_pre
            - snap_post
        required: True
        default: None
    config_file:
        description:
            - The YAML configuration file for the JSNAPy tests
        required: true
        default: None
'''

EXAMPLES = '''
   - name: JUNOS Post Checklist
     junos_jsnapy:
     host: "{{ inventory_hostname}}"
     passwd: "{{ tm1_password }}"
     action: "snap_post"
     config_file: "first_test.yml"
     logfile: "migration_post.log"
     register: jsnapy

   - name: Debug jsnapy
     debug: msg="{{jsnapy}}"

'''
from distutils.version import LooseVersion
import logging
from lxml import etree
from lxml.builder import E

try:
    from jnpr.junos import Device
    from jnpr.junos.version import VERSION
    from jnpr.junos.exception import RpcError
    from jnpr.jsnapy import SnapAdmin
    import os
    import time
    if not LooseVersion(VERSION) >= LooseVersion('1.2.2'):
        HAS_PYEZ = False
    else:
        HAS_PYEZ = True
except ImportError:
    HAS_PYEZ = False


def jsnap_selection(dev, module):

    args = module.params
    action = args['action']
    config_file = args['config_file']
    dir = args['dir']

    config_data = os.path.join(dir, config_file)

    results = dict()
    js = SnapAdmin()

    if action == 'snapcheck':
        snapValue = js.snapcheck(data=config_data, dev=dev)
    elif action == 'snap_pre':
        snapValue = js.snap(data=config_data, dev=dev, file_name='PRE')
    elif action == 'snap_post':
        snapValue = js.snap(data=config_data, dev=dev, file_name='POST')
    elif action == 'check':
        snapValue = js.check(data=config_data, dev=dev, pre_file='PRE', post_file='POST')

    if isinstance(snapValue, (list)):
        for snapCheck in snapValue:
            router = snapCheck.device
            results['router'] = router
            results['final_result'] = snapCheck.result
            results['total_passed'] = snapCheck.no_passed
            results['total_failed'] = snapCheck.no_failed
            total_test = int(snapCheck.no_passed) + int(snapCheck.no_failed)
            results['total_tests'] = total_test
        percentagePassed = (int(results['total_passed']) * 100 ) / (results['total_tests'])
        results['passPercentage'] = percentagePassed

    return results

def main():

    module = AnsibleModule(
        argument_spec=dict(host=dict(required=True, default=None),  # host or ipaddr
                           user=dict(required=False, default=os.getenv('USER')),
                           passwd=dict(required=False, default=None),
                           port=dict(required=False, default=830),
                           logfile=dict(required=False, default=None),
                           config_file=dict(required=False, default=None),
                           dir=dict(required=False, default='/etc/jsnapy/testfiles'),
                           action=dict(required=False, choices=['check', 'snapcheck', 'snap_pre', 'snap_post'], default=None)
                           ),
        supports_check_mode=False)

    if not HAS_PYEZ:
        module.fail_json(msg='junos-eznc >= 1.2.2 is required for this module')

    args = module.params
    results = {}

    logfile = args['logfile']
    if logfile is not None:
        logging.basicConfig(filename=logfile, level=logging.INFO,
                            format='%(asctime)s:%(name)s:%(message)s')
        logging.getLogger().name = 'JSnapy:' + args['host']

    logging.info("connecting to host: {0}@{1}:{2}".format(args['user'], args['host'], args['port']))

    try:
        dev = Device(args['host'], user=args['user'], password=args['passwd'],
                     port=args['port'], gather_facts=False).open()
    except Exception as err:
        msg = 'unable to connect to {0}: {1}'.format(args['host'], str(err))
        logging.error(msg)
        module.fail_json(msg=msg)
        # --- UNREACHABLE ---

    try:
        logging.info("Main program: ")
        results = jsnap_selection(dev, module)

        if 'total_failed' in results and int(results['total_failed']) != 0:
            msg = 'Test Failed: Executed: {0}, Passed {1}, Failed {2}'.format(
                str(results['total_tests']),
                str(results['total_passed']),
                str(results['total_failed'])
            )
            logging.error(msg)
            dev.close()
            module.fail_json(msg=msg)

    except Exception as err:
        msg = 'Uncaught exception - please report: {0}'.format(str(err))
        logging.error(msg)
        dev.close()
        module.fail_json(msg=msg)

    dev.close()

    module.exit_json(**results)

from ansible.module_utils.basic import *
main()