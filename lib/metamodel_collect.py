from .utils import get_json

def objectTodict(obj):
    objtype = type(obj)
    if objtype is int or objtype is str or objtype is float or objtype == type(None) or objtype is bool:
        pass
    elif objtype is dict:
        temp = {}
        for key, value in obj.items():
            temp[key] = objectTodict(value)

        obj = temp
    elif objtype is list:
        temp = []
        for value in obj:
            temp.append(objectTodict(value))
        obj = temp
    else:
        if obj.__dict__ != {}:
            obj = objectTodict(obj.__dict__)
        
    return obj

def get_service_url_from_service_id(base_url, service_id):
    replaced_string = service_id.replace('.', '/')
    return base_url + '/' + replaced_string.replace('_', '-')

def populate_dicts(component_svc, enumeration_dict, structure_dict, service_dict, service_urls_map, base_url):
    components = component_svc.list()
    for component in components:
        component_data = objectTodict(component_svc.get(component))
        component_packages = component_data['info']['packages']
        for package in component_packages.keys():
            package_info = component_packages.get(package)
            for enumeration, enumeration_info in package_info['enumerations'].items():
                enumeration_dict[enumeration] = enumeration_info
            for structure, structure_info in package_info['structures'].items():
                structure_dict[structure] = structure_info
                for enum_name, enum_info in structure_info['enumerations'].items():
                    enumeration_dict[enum_name] = enum_info
            for service, service_info in package_info['services'].items():
                service_dict[service] = service_info
                service_urls_map[get_service_url_from_service_id(base_url, service)] = service
                for structure_name, structure_info in service_info['structures'].items():
                    structure_dict[structure_name] = structure_info
                    for et1, et_info1 in structure_info['enumerations'].items():
                        enumeration_dict[et1] = et_info1
                for enum_name, enum_info in service_info['enumerations'].items():
                    enumeration_dict[enum_name] = enum_info

def get_service_urls_from_rest_navigation(rest_navigation_url, verify=True):

    # Make request to rest end point and get main link to components
    components_url = get_json(rest_navigation_url, verify)['components']['href']
    # make request on main link and get list of all the components
    components = get_json(components_url, verify)

    # get service url link from each component
    component_services_urls = [component['services']['href'] for component in components]

    service_url_dict = {}
    for url in component_services_urls:
        services = get_json(url, verify)
        for service in services:
            service_url_dict[service['href']] = service['name']
    
    return service_url_dict

def categorize_service_urls_by_package_names(service_urls_map, base_url):
    
    package_dict = {}
    for service_url in service_urls_map:
        
        # service_url = u'https://vcip/rest/com/vmware/vapi/metadata/metamodel/resource/model'
        # service_path = /com/vmware/vapi/metadata/metamodel/resource/model
        # package = vapi

        if not service_url.startswith(base_url):
            service_path = service_url
        else:
            service_path =  service_url[len(base_url):]
        
        package = service_path.split('/')[3]
    
        if package in package_dict:
            packages = package_dict[package]
            packages.append(service_url)
    
        else:
            package_dict.setdefault(package, [service_url])
    
    return package_dict