import six

## Function to be exported from this file : visit_type_category and check_type

###
##  1.
###
def visit_type_category(struct_type, new_prop, type_dict, structure_svc, enum_svc):
    if struct_type['category'] == 'BUILTIN':
        visit_builtin(struct_type['builtin_type'], new_prop)
    elif struct_type['category'] == 'GENERIC':
        visit_generic(struct_type['generic_instantiation'], new_prop, type_dict, structure_svc,
                      enum_svc)
    elif struct_type['category'] == 'USER_DEFINED':
        visit_user_defined(struct_type['user_defined_type'], new_prop, type_dict, structure_svc,
                           enum_svc)

#   visit_type_category support functions STARTS

def visit_builtin(builtin_type, new_prop):
    data_type, format_ = metamodel_to_swagger_type_converter(builtin_type)
    if 'type' in new_prop and new_prop['type'] == 'array':
        item_obj = {'type': data_type}
        new_prop['items'] = item_obj
        if format_ is not None:
            item_obj['format'] = format_
    else:
        new_prop['type'] = data_type
        if format_ is not None:
            new_prop['format'] = format_


def visit_generic(generic_instantiation, new_prop, type_dict, structure_svc, enum_svc):
    if generic_instantiation['generic_type'] == 'OPTIONAL':
        new_prop['required'] = False
        visit_type_category(generic_instantiation['element_type'], new_prop, type_dict,
                            structure_svc, enum_svc)
    elif generic_instantiation['generic_type'] == 'LIST':
        new_prop['type'] = 'array'
        visit_type_category(generic_instantiation['element_type'], new_prop, type_dict,
                            structure_svc, enum_svc)
    elif generic_instantiation['generic_type'] == 'SET':
        new_prop['type'] = 'array'
        new_prop['uniqueItems'] = True
        visit_type_category(generic_instantiation['element_type'], new_prop, type_dict,
                            structure_svc, enum_svc)
    elif generic_instantiation['generic_type'] == 'MAP':
        new_type = {'type': 'object', 'properties': {}}
        if generic_instantiation['map_key_type']['category'] == 'USER_DEFINED':
            res_id = generic_instantiation['map_key_type']['user_defined_type']['resource_id']
            res_type = generic_instantiation['map_key_type']['user_defined_type']['resource_type']
            new_type['properties']['key'] = {'$ref': '#/definitions/' + res_id}
            check_type(res_type, res_id, type_dict, structure_svc, enum_svc)
        else:
            new_type['properties']['key'] = {'type': metamodel_to_swagger_type_converter(
                generic_instantiation['map_key_type']['builtin_type'])[0]}
        if generic_instantiation['map_value_type']['category'] == 'USER_DEFINED':
            new_type['properties']['value'] = {
                '$ref': '#/definitions/' + generic_instantiation['map_value_type']['user_defined_type']['resource_id']}
            res_type = generic_instantiation['map_value_type']['user_defined_type']['resource_type']
            res_id = generic_instantiation['map_value_type']['user_defined_type']['resource_id']
            check_type(res_type, res_id, type_dict, structure_svc, enum_svc)
        elif generic_instantiation['map_value_type']['category'] == 'BUILTIN':
            new_type['properties']['value'] = {'type': metamodel_to_swagger_type_converter(
                generic_instantiation['map_value_type']['builtin_type'])[0]}
        elif generic_instantiation['map_value_type']['category'] == 'GENERIC':
            new_type['properties']['value'] = {}
            visit_generic(generic_instantiation['map_value_type']['generic_instantiation'],
                          new_type['properties']['value'], type_dict, structure_svc, enum_svc)
        new_prop['type'] = 'array'
        new_prop['items'] = new_type
        if '$ref' in new_prop:
            del new_prop['$ref']

def visit_user_defined(user_defined_type, newprop, type_dict, structure_svc, enum_svc):
    if user_defined_type['resource_id'] is None:
        return
    if 'type' in newprop and newprop['type'] == 'array':
        item_obj = {'$ref': '#/definitions/' + user_defined_type['resource_id']}
        newprop['items'] = item_obj
    # if not array, fill in type or ref
    else:
        newprop['$ref'] = '#/definitions/' + user_defined_type['resource_id']

    check_type(user_defined_type['resource_type'], user_defined_type['resource_id'], type_dict, structure_svc, enum_svc)

def metamodel_to_swagger_type_converter(input_type):
    """
    Converts API Metamodel type to their equivalent Swagger type.
    A tuple is returned. first value of tuple is main type.
    second value of tuple has 'format' information, if available.
    """
    input_type = input_type.lower()
    if input_type == 'date_time':
        return 'string', 'date-time'
    if input_type == 'secret':
        return 'string', 'password'
    if input_type == 'any_error':
        return 'string', None
    if input_type == 'dynamic_structure':
        return 'object', None
    if input_type == 'uri':
        return 'string', 'uri'
    if input_type == 'id':
        return 'string', None
    if input_type == 'long':
        return 'integer', 'int64'
    if input_type == 'double':
        return 'number', 'double'
    if input_type == 'binary':
        return 'string', 'binary'
    return input_type, None

#   visit_type_category support functions ENDS


###
##  2.
###
def check_type(resource_type, type_name, type_dict, structure_svc, enum_svc):
    if type_name in type_dict or is_type_builtin(type_name):
        return
    if resource_type == 'com.vmware.vapi.structure':
        structure_info = get_structure_info(type_name, structure_svc)
        if structure_info is not None:
            # Mark it as visited to handle recursive definitions. (Type A referring to Type A in one of the fields).
            type_dict[type_name] = {}
            process_structure_info(type_name, structure_info, type_dict, structure_svc, enum_svc)
    else:
        enum_info = get_enum_info(type_name, enum_svc)
        if enum_info is not None:
            # Mark it as visited to handle recursive definitions. (Type A referring to Type A in one of the fields).
            # process enum info
            enum_type = {'type': 'string', 'description': enum_info['documentation']}
            enum_type.setdefault('enum', [value['value'] for value in enum_info['values']])
            type_dict[type_name] = enum_type

#   check_type support functions STARTS

def is_type_builtin(type_):
    type_ = type_.lower()
    typeset = {'binary', 'boolean', 'datetime', 'double', 'dynamicstructure', 'exception',
               'id', 'long', 'opaque', 'secret', 'string', 'uri'}
    if type_ in typeset:
        return True
    return False

def get_structure_info(struct_type, structure_svc):
    """
    Given a type, return its structure info, if the type is a structure.
    """
    try:
        structure_info = structure_svc.get(struct_type)
        if structure_info is None:
            eprint("Could not fetch structure info for " + struct_type)
        return structure_info
    except Exception as ex:
        eprint("Error fetching structure info for " + struct_type)
        eprint(ex)
        return None

def process_structure_info(type_name, structure_info, type_dict, structure_svc, enum_svc):
    new_type = {'type': 'object', 'properties': {}}
    for field in structure_info['fields']:
        newprop = {'description': field['documentation']}
        if field['type']['category'] == 'BUILTIN':
            visit_builtin(field['type']['builtin_type'], newprop)
        elif field['type']['category'] == 'GENERIC':
            visit_generic(field['type']['generic_instantiation'], newprop, type_dict,
                          structure_svc, enum_svc)
        elif field['type']['category'] == 'USER_DEFINED':
            visit_user_defined(field['type']['user_defined_type'], newprop, type_dict,
                               structure_svc, enum_svc)
        new_type['properties'].setdefault(field['name'], newprop)
    required = []
    for property_name, property_value in six.iteritems(new_type['properties']):
        if 'required' not in property_value:
            required.append(property_name)
        elif property_value['required'] == 'true':
            required.append(property_name)
    if len(required) > 0:
        new_type['required'] = required
    type_dict[type_name] = new_type


def get_enum_info(type_name, enum_svc):
    """
    Given a type, return its enum info, if the type is enum.
    """
    try:
        enum_info = enum_svc.get(type_name)
        if enum_info is None:
            eprint("Could not fetch enum info for " + type_name)
        return enum_info
    except Exception as exception:
        eprint("Error fetching enum info for " + type_name)
        eprint(exception)
        return None

#   check_type support functions ENDS