import re

from .type_handler import visit_type_category
import six

class paramsHandler():
    def __init__(self, url, method_type, service_name, operation_name, params_metadata, type_dict, structure_svc, enum_svc):

        self.url = url
        self.method_type = method_type
        self.service_name = service_name
        self.operation_name = operation_name
        self.params = params_metadata
        self.type_dict = type_dict
        self.structure_svc = structure_svc
        self.enum_svc = enum_svc

        self.params_array = []

        
        path_param_list, other_params, self.url = self.extract_path_parameters()
        for field_info in path_param_list:
            param = self.convert_field_info_to_swagger_parameter('path', field_info)
            self.params_array.append(param)

        if self.method_type in ('post', 'put', 'patch'):
            # Handles http post/put/patch request.
            # todo: handle query, formData and header parameters
            if other_params:
                param = self.wrap_body_params(service_name, operation_name, other_params)
                if param is not None:
                    self.params_array.append(param)
        
        elif self.method_type == 'get':
            for field_info in other_params:
                param = self.flatten_query_param_spec(field_info)
                if param is not None:
                    self.params_array[1:1] = param

        elif self.method_type == 'delete':
            for field_info in other_params:
                param = self.convert_field_info_to_swagger_parameter('query', field_info)
                self.params_array.append(param)

    def convert_field_info_to_swagger_parameter(self, param_type, field_info):
        """
        Converts metamodel fieldinfo to swagger parameter.
        """
        param = {}
        visit_type_category(field_info['type'], param, self.type_dict, self.structure_svc, self.enum_svc)

        if 'required' not in param:
            param['required'] = True

        param['in'] = param_type
        param['name'] = field_info['name']
        param['description'] = field_info['documentation']

        # $ref should be encapsulated in 'schema' instead of parameter.
        if '$ref' in param:
            schema_obj = {'$ref': param['$ref']}
            param['schema'] = schema_obj
            del param['$ref']
        return param

    def extract_path_parameters(self):
        """
        Return list of field_infos which are path variables, another list of
        field_infos which are not path parameters and the url that eventually
        changed due to mismatching param names.
        An example of a URL that changes:
        /vcenter/resource-pool/{resource-pool} to
        /vcenter/resource-pool/{resource_pool}
        """
        params, url = self.params, self.url
        # Regex to look for {} placeholders with a group to match only the parameter name
        re_path_param = re.compile('{(.+?)}')
        path_params = []
        other_params = list(params)
        new_url = url
        for path_param_name_match in re_path_param.finditer(url):
            path_param_placeholder = path_param_name_match.group(1)
            path_param_info = None
            for param in other_params:
                if is_param_path_variable(param, path_param_placeholder):
                    path_param_info = param
                    if param['name'] != path_param_placeholder:
                        new_url = new_url.replace(path_param_name_match.group(), '{' + param['name'] + '}')
                    break
            if path_param_info is None:
                eprint('%s parameter from %s is not found among the operation\'s parameters'
                    % (path_param_placeholder, url))
            else:
                path_params.append(path_param_info)
                other_params.remove(path_param_info)
        return path_params, other_params, new_url

    def flatten_query_param_spec(self, query_param_info):
        """
        Flattens query parameters specs.
        1. Create a query parameter for every field in spec.
            Example 1:
                consider datacenter get which accepts optional filterspec.
                Optional<Datacenter.FilterSpec> filter)
                The method would convert the filterspec to 3 separate query parameters
                filter.datacenters, filter.names and filter.folders.
            Example 2:
                consider /vcenter/deployment/install/initial-config/remote-psc/thumbprint get
                which accepts parameter
                vcenter.deployment.install.initial_config.remote_psc.thumbprint.remote_spec.
                The two members defined under remote_spec
                address and https_port are converted to two separate query parameters
                address(required) and https_port(optional).
        2. The field info is simple type. i.e the type is string, integer
            then it is converted it to swagger parameter.
            Example:
                consider /com/vmware/content/library/item get
                which accepts parameter 'library_id'. The field is converted
                to library_id query parameter.
        3. This field has references to a spec but the spec is not
            a complex type and does not have property 'properties'.
            i.e the type is string, integer. The members defined under the spec are
            converted to query parameter.
            Example:
                consider /appliance/update/pending get which accepts two parameter
                'source_type' and url. Where source_type is defined in the spec
                'appliance.update.pending.source_type' and field url
                is of type string.
                The fields 'source_type' and 'url' are converted to query parameter
                of type string.
        """
        prop_array = []
        parameter_obj = {}
        visit_type_category(query_param_info['type'], parameter_obj, self.type_dict, self.structure_svc, self.enum_svc)
        if '$ref' in parameter_obj:
            reference = parameter_obj['$ref'].replace('#/definitions/', '')
            type_ref = self.type_dict.get(reference, None)
            if type_ref is None:
                return None
            if 'properties' in type_ref:
                for property_name, property_value in six.iteritems(type_ref['properties']):
                    prop = {'in': 'query', 'name': query_param_info['name'] + '.' + property_name}
                    if 'type' in property_value:
                        prop['type'] = property_value['type']
                        if prop['type'] == 'array':
                            prop['collectionFormat'] = 'multi'
                            prop['items'] = property_value['items']
                            if '$ref' in property_value['items']:
                                ref = property_value['items']['$ref'].replace('#/definitions/', '')
                                type_ref = self.type_dict[ref]
                                prop['items'] = type_ref
                                if 'description' in prop['items']:
                                    del prop['items']['description']
                        if 'description' in property_value:
                            prop['description'] = property_value['description']
                    elif '$ref' in property_value:
                        reference = property_value['$ref'].replace('#/definitions/', '')
                        prop_obj = self.type_dict[reference]
                        if 'type' in prop_obj:
                            prop['type'] = prop_obj['type']
                        if 'enum' in prop_obj:
                            prop['enum'] = prop_obj['enum']
                        if 'description' in prop_obj:
                            prop['description'] = prop_obj['description']
                    if 'required' in type_ref:
                        if property_name in type_ref['required']:
                            prop['required'] = True
                        else:
                            prop['required'] = False
                    prop_array.append(prop)
            else:
                prop = {'in': 'query', 'name': query_param_info['name'], 'description': type_ref['description'],
                        'type': type_ref['type']}
                if 'enum' in type_ref:
                    prop['enum'] = type_ref['enum']
                if 'required' not in parameter_obj:
                    prop['required'] = True
                else:
                    prop['required'] = parameter_obj['required']
                prop_array.append(prop)
        else:
            parameter_obj['in'] = 'query'
            parameter_obj['name'] = query_param_info['name']
            parameter_obj['description'] = query_param_info['documentation']
            if 'required' not in parameter_obj:
                parameter_obj['required'] = True
            prop_array.append(parameter_obj)
        return prop_array

    def wrap_body_params(self, service_name, operation_name, body_param_list):
        """
        Creates a  json object wrapper around request body parameters. parameter names are used as keys and the
        parameters as values.
        For instance, datacenter create operation takes CreateSpec whose parameter name is spec.
        This method creates a json wrapper object
        datacenter.create {
        'spec' : {spec obj representation  }
        }
        """
        # todo: 
        # not unique enough. make it unique
        wrapper_name = service_name + '_' + operation_name
        body_obj = {'type': 'object'}
        properties_obj = {}
        body_obj['properties'] = properties_obj
        required = []
        # name_array = [] ##### WHY do we need it ?
        for param in body_param_list:
            parameter_obj = {}
            visit_type_category(param['type'], parameter_obj, self.type_dict, self.structure_svc, self.enum_svc)
            # name_array.append(param['name'])
            parameter_obj['description'] = param['documentation']
            properties_obj[param['name']] = parameter_obj

            if 'required' not in parameter_obj:
                required.append(param['name'])
            else:
                if parameter_obj['required'] == True:
                    required.append(param['name'])

        parameter_obj = {'in': 'body', 'name': 'request_body'}
        if len(required) > 0:
            body_obj['required'] = required
            parameter_obj['required'] = True

        self.type_dict[wrapper_name] = body_obj

        schema_obj = {'$ref': '#/definitions/' + wrapper_name}
        parameter_obj['schema'] = schema_obj
        return parameter_obj

def is_param_path_variable(param, path_param_placeholder):
    if param['name'] == path_param_placeholder:
        return True
    if 'PathVariable' not in param['metadata']:
        return False
    return param['metadata']['PathVariable']['elements']['value']['string_value'] == path_param_placeholder