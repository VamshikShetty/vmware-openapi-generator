import collections
import six
import re
import os

from .utils import build_error_map, get_json, write_json_data_to_file, load_description
from .parameter_handler import paramsHandler
from .response_handler import populate_response_map

def contains_rm_annotation(service_info):
    for operation in service_info['operations'].values():
        if 'RequestMapping' not in operation['metadata']:
            return False
    return True

def get_path(operation_info, http_method, url, service_name, type_dict, structure_dict, enum_dict, operation_id, error_map, tag_separator, spec):
    
    documentation = operation_info['documentation']
    params = operation_info['params']
    errors = operation_info['errors']
    output = operation_info['output']
    http_method = http_method.lower()

    # find consume
    consumes =  None
    if http_method not in ('get', 'delete') and spec == '2':
        consumes =  ['application/json']

    produces = None

    phandler = paramsHandler(url, http_method, service_name,
                                            operation_id, params, type_dict,
                                            structure_dict, enum_dict, spec)
    
    param_array, url, request_body = phandler.params_array, phandler.url, phandler.request_body

    responses = populate_response_map(output,
                                         errors,
                                         error_map, type_dict, structure_dict, enum_dict, service_name, operation_id, spec)

    path_obj = {}

    path_obj['tags'] = [tag_separator.join(service_name.split('.')[3:])]
    if http_method is not None:
        path_obj['method'] = http_method
    if url is not None:
        path_obj['path'] = url
    if documentation is not None:
        path_obj['summary'] = documentation
    if param_array is not None:
        path_obj['parameters'] = param_array
    if request_body is not None:
        path_obj['requestBody'] = request_body
    if responses is not None:
        path_obj['responses'] = responses
    if consumes is not None:
        path_obj['consumes'] = consumes
    if produces is not None:
        path_obj['produces'] = produces
    if operation_id is not None:
        path_obj['operationId'] = operation_id
    
    if path_obj['path'] == '/com/vmware/cis/session' and path_obj['method'] == 'post':
        header_parameter = {'in': 'header', 'required': True,
                            'name': 'vmware-use-header-authn',
                            'description': 'Custom header to protect against CSRF attacks in browser based clients'}
        
        if spec == '2':
            header_parameter['type'] = 'string'
            path_obj['security'] = [{'basic_auth': []}]
        elif spec == '3':
            header_parameter['schema'] = { 'type' : 'string' }

        path_obj['parameters'] = [header_parameter]

    return path_obj

def find_url(list_of_links):
    """
    There are many apis which get same work done.
    The idea here is to show the best one.
    Here is the logic for picking the best one.
    * if there is only one element in the list, the choice is obvious.
    * if there are more than one:
        return for a link which does not contain "~action" in them and which contain "id:{}" in them.
    """
    if len(list_of_links) == 1:
        return list_of_links[0]['href'], list_of_links[0]['method']

    non_action_link = None
    for link in list_of_links:
        if '~action=' not in link['href']:
            if "id:" in link['href']:
                return link['href'], link['method']
            if non_action_link is None:
                non_action_link = link
    if non_action_link is None:
        # all links have ~action in them. check if any of them has id: and return it.
        for link in list_of_links:
            if "id:" in link['href']:
                return link['href'], link['method']

        # all links have ~action in them and none of them have id: (pick any one)
        return list_of_links[0]['href'], list_of_links[0]['method']

    return non_action_link['href'], non_action_link['method']

def process_service_urls(package_name, service_urls, output_dir, structure_dict, enum_dict,
                         service_dict, service_url_dict, base_url, generate_unique_op_ids, tag_separator, spec):

    type_dict = {}
    path_list = []
    error_map = build_error_map()

    for service_url in service_urls:
        service_name = service_url_dict.get(service_url, None)
        service_info = service_dict.get(service_name, None)

        if service_info is None:
            continue

        if contains_rm_annotation(service_info):
            for operation in service_info['operations'].values():
                url, method = find_url_method(operation)
                operation_id = operation['name']
                operation_info = service_info['operations'].get(operation_id)

                path = get_path(operation_info, method, url, service_name, type_dict, structure_dict, enum_dict,
                                operation_id, error_map, tag_separator, spec)
                path_list.append(path)
            continue

        # use rest navigation service to get the REST mappings for a service.
        service_operations = get_json(service_url + '?~method=OPTIONS', False)
        if service_operations is None:
            continue

        for service_operation in service_operations:
            service_name = service_operation['service']
            # service_info must be re-assigned when service_operations are obtained through ?~method=OPTIONS.
            # this is because all service operations matching the prefix of the service is returned instead of returning
            # only operations which has exact match.
            # for example OPTIONS on com.vmware.content.library returns operations from following services
            # instead of just com.vmware.content.library.item
            # com.vmware.content.library.item.storage
            # com.vmware.content.library.item
            # com.vmware.content.library.item.file
            # com.vmware.content.library.item.update_session
            # com.vmware.content.library.item.updatesession.file
            service_info = service_dict.get(service_name, None)
            if service_info is None:
                continue

            operation_id = service_operation['name']
            if operation_id not in service_info['operations']:
                continue

            url, method = find_url(service_operation['links'])
            
            if url.startswith(base_url):
                url = url[len(base_url):]

            operation_info = service_info['operations'].get(operation_id)
            path = get_path(operation_info, method, url, service_name, type_dict, structure_dict, enum_dict,
                            operation_id, error_map, tag_separator, spec)
            path_list.append(path)

    # The same path can have multiple methods.
    # For example: /vcenter/vm can have 'get', 'patch', 'put'
    # Rearrange list into a map/object which is the format expected by swagger-ui
    # key is the path ie. /vcenter/vm/
    # value is a an object which contains key as method names and value as path objects
    path_dict = {}
    for path in path_list:
        x = path_dict.get(path['path'])
        if x is None:
            x = {path['method']: path}
            path_dict[path['path']] = x
        else:
            x[path['method']] = path

    cleanup(path_dict=path_dict, type_dict=type_dict)
    process_output(path_dict, type_dict, output_dir, package_name, generate_unique_op_ids, spec)

def find_url_method(opinfo):
    """
    Given OperationInfo, find url and method if it exists
    :param opinfo:
    :return:
    """
    params = None
    url = None
    method = None
    if 'RequestMapping' in opinfo['metadata']:
        element_map = opinfo['metadata']['RequestMapping']
        if 'value' in element_map['elements']:
            element_value = element_map['elements']['value']
            url = element_value['string_value']
        if 'method' in element_map['elements']:
            element_value = element_map['elements']['method']
            method = element_value['string_value']
        if 'params' in element_map['elements']:
            element_value = element_map['elements']['params']
            params = element_value['string_value']
    if params is not None:
        url = url + '?' + params
    return url, method

def cleanup(path_dict, type_dict):
    for _, type_object in six.iteritems(type_dict):
        if 'properties' in type_object:
            properties = type_object['properties']
            for _, property_value in six.iteritems(properties):
                if 'required' in property_value and isinstance(property_value['required'], bool):
                    del property_value['required']
    for _, path_value in six.iteritems(path_dict):
        for _, method_value in six.iteritems(path_value):
            if 'path' in method_value:
                del method_value['path']
            if 'method' in method_value:
                del method_value['method']

def process_output(path_dict, type_dict, output_dir, output_filename, generate_unique_op_ids, spec):
    description_map = load_description()
    remove_com_vmware_from_dict(path_dict)
    if generate_unique_op_ids:
        create_unique_op_ids(path_dict)
    remove_query_params(path_dict, spec)
    remove_com_vmware_from_dict(type_dict)
    if spec == '2':
        swagger_template = {'swagger': '2.0',
                            'info': {'description': description_map.get(output_filename, ''),
                                    'title': output_filename,
                                    'termsOfService': 'http://swagger.io/terms/',
                                    'version': '2.0.0'}, 
                            'host': '<vcenter>',
                            'securityDefinitions': {'basic_auth': {'type': 'basic'}},
                            'basePath': '/rest', 'tags': [],
                            'schemes': ['https', 'http'],
                            'paths': collections.OrderedDict(sorted(path_dict.items())),
                            'definitions': collections.OrderedDict(sorted(type_dict.items()))
                            }
    elif spec == '3':
        remove_com_vmware_from_dict(type_dict['requestBodies'])
        swagger_template = {'openapi': '3.0.0',
                            'info': {'description': description_map.get(output_filename, ''),
                                    'title': output_filename,
                                    'termsOfService': 'http://swagger.io/terms/',
                                    'version': '2.0.0'},
                            'paths': collections.OrderedDict(sorted(path_dict.items())),
                            'components': {
                                'requestBodies': collections.OrderedDict(sorted(type_dict['requestBodies'].items()))
                                 #,
                                # 'securitySchemes':{'basic_auth': {'type': 'basic'}}
                            }
                        }
        del type_dict['requestBodies']
        swagger_template['components']['schemas'] = collections.OrderedDict(sorted(type_dict.items()))

    write_json_data_to_file(output_dir + os.path.sep + output_filename + '.json', swagger_template)

def create_unique_op_ids(path_dict):
    """
    Creates unique operation ids
    Takes the path dictionary as input parameter:
    1. Iterates through all the http_operation array
    2. For every operation gets the current operation id
    3. Calls method to get the camelized operation id
    4. Checks for uniqueness
    5. Updates the path dictionary with the unique operation id
    
    :param path_dict:
    """
    op_id_list = ['get', 'set', 'list', 'add', 'run', 'start', 'stop',
                  'restart', 'reset', 'cancel', 'create', 'update', 'delete']
    for path, http_operation in path_dict.items():
        for http_method, operation_dict in http_operation.items():
            op_id_val = create_camelized_op_id(path, http_method, operation_dict)
            if op_id_val not in op_id_list:
                operation_dict['operationId'] = op_id_val
                op_id_list.append(op_id_val)

def remove_com_vmware_from_dict(swagger_obj, depth=0, keys_list=[]):
    """
    The method
    1. removes 'com.vmware.' from model names
    2. replaces $ with _ from the model names

    This is done on both definitions and path
    'definitions' : where models are defined and may be referenced.
    'path' : where models are referenced.
    :param swagger_obj: should be path of definitions dictionary
    :param depth: depth of the dictionary. Defaults to 0
    :param keys_list: List of updated model names
    :return:
    """
    if isinstance(swagger_obj, dict):
        if '$ref' in swagger_obj and 'required' in swagger_obj:
            del swagger_obj['required']
        for key, item in swagger_obj.items():
            if isinstance(item, str):
                if key in ('$ref', 'summary', 'description'):
                    item = item.replace('com.vmware.', '')
                    if key == '$ref':
                        item = item.replace('$', '_')
                    swagger_obj[key] = item
            elif isinstance(item, list):
                for itm in item:
                    remove_com_vmware_from_dict(itm, depth+1, keys_list)
            elif isinstance(item, dict):
                if depth == 0 and isinstance(key, str) and (key.startswith('com.vmware.') or '$' in key):
                    keys_list.append(key)
                remove_com_vmware_from_dict(item, depth+1, keys_list)
    elif isinstance(swagger_obj, list):
        for itm in swagger_obj:
            remove_com_vmware_from_dict(itm, depth+1)
    if depth == 0 and len(keys_list) > 0:
        while keys_list:
            old_key = keys_list.pop()
            new_key = old_key.replace('com.vmware.', '')
            new_key = new_key.replace('$', '_')
            try:
                swagger_obj[new_key] = swagger_obj.pop(old_key)
            except KeyError:
                print('Could not find the Swagger Element :  {}'.format(old_key))

def remove_query_params(path_dict, spec):
    """
    Swagger/Open API specification prohibits appending query parameter to the request mapping path.

    Duplicate paths in Open API :
        Since request mapping paths are keys in the Open Api JSON, there is no scope of duplicate request mapping paths

    Partial Duplicates in Open API: APIs which have same request mapping paths but different HTTP Operations.

    Such Operations can be merged together under one path
        eg: Consider these two paths
            /A/B/C : [POST]
            /A/B/C : [PUT]
        On merging these, the new path would look like:
        /A/B/C : [POST, PUT]

    Absolute Duplicates in Open API: APIs which have same request mapping path and HTTP Operation(s)
        eg: Consider two paths
            /A/B/C : [POST, PUT]
            /A/B/C : [PUT]
    Such paths can not co-exist in the same Open API definition.

    This method attempts to move query parameters from request mapping url to parameter section.

    There are 4 possibilities which may arise on removing the query parameter from request mapping path:

     1. Absolute Duplicate
        The combination of path and the HTTP Operation Type(s)are same to that of an existing path:
        Handling Such APIs is Out of Scope of this method. Such APIs will appear in the Open API definition unchanged.
        Example :
                /com/vmware/cis/session?~action=get : [POST]
                /com/vmware/cis/session : [POST, DELETE]
    2. Partial Duplicate:
        The Paths are same but the HTTP operations are Unique:
        Handling Such APIs involves adding the Operations of the new duplicate path to that of the existing path
        Example :
                /cis/tasks/{task}?action=cancel : [POST]
                /cis/tasks/{task} : [GET]
    3. New Unique Path:
        The new path is not a duplicate of any path in the current Open API definition.
        The Path is changed to new path by trimming off the path post '?'

    4. The duplicate paths are formed when two paths with QueryParameters are fixed
        All the scenarios under 1, 2 and 3 are possible.
        Example :
                /com/vmware/cis/tagging/tag-association/id:{tag_id}?~action=detach-tag-from-multiple-objects
                /com/vmware/cis/tagging/tag-association/id:{tag_id}?~action=list-attached-objects
    :param path_dict:
    """
    paths_to_delete = []
    for old_path, http_operations in path_dict.items():
        if '?' in old_path:
            paths_array = re.split('\?', old_path)
            new_path = paths_array[0]
            query_parameters = paths_array[1]
            key_value = query_parameters.split('=')

            q_param = {'name': key_value[0], 
                        'in': 'query', 
                        'description': key_value[0] + '=' + key_value[1],
                        'required': True
                        }

            if spec == '2':
                q_param['type'] = 'string'
                q_param['enum'] = [key_value[1]]
            elif spec == '3':
                q_param['schema'] = {}
                q_param['schema']['type'] = 'string'
                q_param['schema']['enum'] = [key_value[1]]

            if new_path in path_dict:
                new_path_operations = path_dict[new_path].keys()
                path_operations = http_operations.keys()
                if len(set(path_operations).intersection(new_path_operations)) < 1:
                    for http_method, operation_dict in http_operations.items():
                        operation_dict['parameters'].append(q_param)
                    
                    temp = http_operations.copy()
                    temp.update(path_dict[new_path])
                    path_dict[new_path] = temp

                    paths_to_delete.append(old_path)
            else:
                for http_method, operation_dict in http_operations.items():
                    operation_dict['parameters'].append(q_param)
                path_dict[new_path] = path_dict.pop(old_path)
    for path in paths_to_delete:
        del path_dict[path]

def create_camelized_op_id(path, http_method, operations_dict):
    """
    Creates camelized operation id.
    Takes the path, http_method and operation dictionary as input parameter:
    1. Iterates through all the operation array to return the current operation id
    2. Appends path to the existing operation id and
     replaces '/' and '-' with '_' and removes 'com_vmware_'
    3. Splits the string by '_'
    4. Converts the first letter of all the words except the first one from lower to upper
    5. Joins all the words together and returns the new camelcase string
    e.g
        parameter : abc_def_ghi
        return    : AbcDefGhi
    :param path:
    :param http_method:
    :param operations_dict:
    :return: new_op_id
    """
    curr_op_id = operations_dict['operationId']
    raw_op_id = curr_op_id.replace('-', '_')
    new_op_id = raw_op_id
    if '_' in raw_op_id:
        raw_op_id_iter = iter(raw_op_id.split('_'))
        new_op_id = next(raw_op_id_iter)
        for new_op_id_element in raw_op_id_iter:
            new_op_id += new_op_id_element.title()
    ''' 
        Removes query parameters form the path. 
        Only path elements are used in operation ids
    '''
    paths_array = re.split('\?', path)
    path = paths_array[0]
    path_elements = path.replace('-', '_').split('/')
    path_elements_iter = iter(path_elements)
    for path_element in path_elements_iter:
        if '{' in path_element:
            continue
        if 'com' == path_element or 'vmware' == path_element:
            continue
        if path_element.lower() == raw_op_id.lower():
            continue
        if '_' in path_element:
            sub_path_iter = iter(path_element.split('_'))
            for sub_path_element in sub_path_iter:
                new_op_id += sub_path_element.title()
        else:
            new_op_id += path_element.title()
    return new_op_id