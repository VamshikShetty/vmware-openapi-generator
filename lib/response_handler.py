from six.moves import http_client
import requests

from .type_handler import check_type, visit_type_category

def populate_response_map(output, errors, error_map, type_dict, structure_svc, enum_svc, service_id, operation_id, spec):
    response_map = {}

    if spec == '2':
        ref_path = "#/definitions/"
        success_response = {'description': output['documentation']}
    elif spec == '3':
        ref_path = "#/components/schemas/"
        success_response = {
            'description': output['documentation'], 
            'content':{ 
                'application/json':{
                } 
            }
        }

    schema = {}
    visit_type_category(output['type'], schema, type_dict, structure_svc, enum_svc, ref_path)

    # if type of schema is void, don't include it.
    # this prevents showing response as void in swagger-ui



    if schema is not None:
        if not ('type' in schema and schema['type'] == 'void'):
            value_wrapper = {'type': 'object',
                             'properties': {'value': schema},
                             'required': ['value']}

            # get response object name
            if operation_id == 'get':
                type_name = service_id
            else:
                type_name = service_id + '.' + operation_id
            
            type_name = type_name + '_result'

            if type_name not in type_dict:
                type_dict[type_name] = value_wrapper

            if spec == '2':
                success_response['schema'] = {"$ref": ref_path + type_name}
            elif spec == '3':
                success_response['content']['application/json']['schema'] = {"$ref": ref_path + type_name}


    # success response is not mapped through metamodel.
    # hardcode it for now.
    response_map[requests.codes.ok] = success_response
    for error in errors:
        status_code = error_map.get(error['structure_id'], http_client.INTERNAL_SERVER_ERROR)
        check_type('com.vmware.vapi.structure', error['structure_id'], type_dict, structure_svc, enum_svc, spec)
        schema_obj = {
            'type': 'object', 
            'description': error['documentation'],
            'properties': {
                'type': {
                    'type': 'string'
                },
                'value': {
                    '$ref': ref_path + error['structure_id']
                }
            }
        }
        type_dict[error['structure_id'] + '_error'] = schema_obj
        response_obj = { '$ref': ref_path + error['structure_id'] + '_error'}
        response_map[status_code] = response_obj

    return response_map