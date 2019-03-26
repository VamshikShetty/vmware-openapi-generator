#!/usr/bin/env python

# Copyright 2016-2018 VMware, Inc.
# SPDX-License-Identifier: MIT

# pylint: disable=C0111, E1121, R0913, R0914, R0911, W0703, E1101, C0301, W0511,C0413
from __future__ import print_function
import six

from vmware.vapi.lib.connect import get_requests_connector
from vmware.vapi.stdlib.client.factories import StubConfigurationFactory
from com.vmware.vapi.metadata import metamodel_client
import os
import argparse
import timeit
import json
import threading
import requests
import warnings

from lib.metamodel_collect import populate_dicts, get_service_urls_from_rest_navigation, categorize_service_urls_by_package_names
from lib.metamodel2openapi import process_service_urls
from lib.utils import write_json_data_to_file

warnings.filterwarnings("ignore")


'''
This script uses metamodel apis and rest navigation to generate openapi json files
for apis available on vcenter.
'''

GENERATE_UNIQUE_OP_IDS = False
TAG_SEPARATOR = '/'
SPECIFICATION = '2'


def get_input_params():
    """
    Gets input parameters from command line
    :return:
    """
    parser = argparse.ArgumentParser(description='Generate swagger.json files for apis on vcenter')
    parser.add_argument('-m', '--metadata-url', help='URL of the metadata API')
    parser.add_argument('-rn', '--rest-navigation-url', help='URL of the rest-navigation API')
    parser.add_argument('-vc', '--vcip', help='IP Address of vCenter Server. If specified, would be used'
                                              ' to calculate metadata-url and rest-navigation-url')
    parser.add_argument('-o', '--output', help='Output directory of swagger files. if not specified,'
                                               ' current working directory is chosen as output directory')
    parser.add_argument('-oas', '--oas', default='2', help='opeanpi spec version')
    parser.add_argument('-s', '--tag-separator', default='/', help='Separator to use in tag name')
    parser.add_argument('-k', '--insecure', action='store_true', help='Bypass SSL certificate validation')
    parser.add_argument("-uo", "--unique-operation-ids", required=False, nargs='?', const=True, default=False,
                        help="Pass this parameter to generate Unique Operation Ids.")
    args = parser.parse_args()
    
    metadata_url = args.metadata_url
    rest_navigation_url = args.rest_navigation_url
    
    vcip = args.vcip
    if vcip is not None:
        if metadata_url is None:
            metadata_url = 'https://%s/api' % vcip
        if rest_navigation_url is None:
            rest_navigation_url = 'https://%s/rest' % vcip
    
    if metadata_url is None or rest_navigation_url is None:
        raise ValueError('metadataUrl and restNavigationUrl are required parameters')
    
    metadata_url = metadata_url.rstrip('/')
    rest_navigation_url = rest_navigation_url.rstrip('/')
    output_dir = args.output
    if output_dir is None:
        output_dir = os.getcwd()

    verify = not args.insecure
    
    global GENERATE_UNIQUE_OP_IDS
    GENERATE_UNIQUE_OP_IDS = args.unique_operation_ids
    
    global TAG_SEPARATOR
    TAG_SEPARATOR = args.tag_separator
    
    global SPECIFICATION
    SPECIFICATION = args.oas
    if SPECIFICATION not in ['2', '3']:
        raise Exception(" Input Valid Specification ")
    return metadata_url, rest_navigation_url, output_dir, verify

def main():
    # Get user input.
    metadata_api_url, rest_navigation_url, output_dir, verify = get_input_params()
    # Maps enumeration id to enumeration info
    enumeration_dict = {}
    # Maps structure_id to structure_info
    structure_dict = {}
    # Maps service_id to service_info
    service_dict = {}
    # Maps service url to service id
    service_urls_map = {}

    start = timeit.default_timer()
    print('Trying to connect ' + metadata_api_url)
    session = requests.session()
    session.verify = False
    connector = get_requests_connector(session, url=metadata_api_url)
    
    print('Connected to ' + metadata_api_url)
    stub_config = StubConfigurationFactory.new_std_configuration(connector)
    component_svc = metamodel_client.Component(stub_config)

    # Get meta model data
    populate_dicts(component_svc, enumeration_dict, structure_dict, service_dict, service_urls_map, rest_navigation_url)

    service_urls_map = get_service_urls_from_rest_navigation(rest_navigation_url, verify)
    package_dict = categorize_service_urls_by_package_names(service_urls_map, rest_navigation_url)

    global GENERATE_UNIQUE_OP_IDS
    global TAG_SEPARATOR
    global SPECIFICATION

    threads = []
    for package, service_urls in six.iteritems(package_dict):
        print('processing package ' + package)
        # if package == 'content':
        worker = threading.Thread(
            target=process_service_urls, 
            args=(
                package, 
                service_urls, 
                output_dir, 
                structure_dict, 
                enumeration_dict, 
                service_dict, 
                service_urls_map, 
                rest_navigation_url,
                GENERATE_UNIQUE_OP_IDS,
                TAG_SEPARATOR,
                SPECIFICATION
            )
        )
        worker.daemon = True
        worker.start()
        threads.append(worker)
    for worker in threads:
        worker.join()

    # api.json contains list of packages which is used by UI to dynamically populate dropdown.
    api_files = {'files': list(package_dict.keys())}
    write_json_data_to_file(output_dir + os.path.sep + 'api.json', api_files)
    stop = timeit.default_timer()
    print('Generated swagger files at ' + output_dir + ' for ' + metadata_api_url + ' in ' + str(
        stop - start) + ' seconds')


if __name__ == '__main__':
    main()
