This is the documentation of how vmware openapi generator works and its workflow details with explanation of each function's work and execution, Before diving into this documentaion make sure you are familiar with the structure of openapi specification file.

Now will start with dividing the main program into 6 different parts.
```
def main():

    ## PART - 1 ##
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



    ## PART - 2 ##
    start = timeit.default_timer()
    print('Trying to connect ' + metadata_api_url)
    session = requests.session()
    session.verify = False
    connector = get_requests_connector(session, url=metadata_api_url)
    print('Connected to ' + metadata_api_url)
    component_svc = get_component_service(connector)



    ## PART - 3 ##
    populate_dicts(component_svc, enumeration_dict, structure_dict, service_dict, service_urls_map, rest_navigation_url)



    ## PART - 4 ##
    service_urls_map = get_service_urls_from_rest_navigation(rest_navigation_url, verify)
    package_dict = categorize_service_urls_by_package_names(service_urls_map, rest_navigation_url)
    error_map = build_error_map()



    ## PART - 5 ##
    threads = []
    for package, service_urls in six.iteritems(package_dict):
        worker = threading.Thread(target=process_service_urls, args=(
            package, service_urls, output_dir, structure_dict, enumeration_dict, service_dict, service_urls_map, error_map, rest_navigation_url))
        worker.daemon = True
        worker.start()
        threads.append(worker)
    for worker in threads:
        worker.join()



    ## PART - 6 ##
    # api.json contains list of packages which is used by UI to dynamically populate dropdown.
    api_files = {'files': list(package_dict.keys())}
    write_json_data_to_file(output_dir + os.path.sep + 'api.json', api_files)
    stop = timeit.default_timer()
    print('Generated swagger files at ' + output_dir + ' for ' + metadata_api_url + ' in ' + str(stop - start) + ' seconds')
```

## Part - 1
This section talks about nothing more than basic setup done to take user's input such vcenter ip or url for metadata and rest navigation whose requirements will be cleared in coming sections. This section also shows initalization of important data structure which will hold informations provided by the metamodel client that are needed to produce the openapi specification file, whose need will be elabroated in there respective parts where they are used.

```get_input_params()``` is a function which can take following parameter values as input.
1. vcip: IP Address of vCenter Server. If specified, would be used to calculate metadata-url and rest-navigation-url
2. metadata_url: URL of the metadata API. In the event vcip is provided then metadata url will be - https://\<vcip\>/api
3. rest_navigation_url: URL of the rest-navigation. In the event vcip is provided then rest navigation url will be API https://\<vcip\>/rest
4. output: Output directory of swagger files. if not specified, current working directory is chosen as output directory
5. tag-separator: Separator to use in tag name
6. insecure: Bypass SSL certificate validation, If not passed program will check for SSL certificate validation
7. unique_operation_ids: Pass this parameter to generate Unique Operation Ids, by default its False. This forces each operation in openapi sepcs even one under different path to have unqiue operations/function name which is a required semantic rule of openapi specification but if ignored the file generated will fail the openapi validation and throw semantic error.

This function returns back four values namely metadata_url, rest_navigation_url, output_dir, verify (insecure) which are self explainatory from the above context.

## Part - 2

First a Session object is created, which allows us to persist certain parameters across requests and will use urllib3’s connection pooling. ```get_requests_connector()``` function takes in session object and metadata url to Create a connection to a vAPI Provider, In vcenter server vAPI Provider is a process which converts vmodel specification to metamodel and provides it in the format of required message protocal, which is json in our case. vAPI provider is acessed through Json RPC client which hits /api end point hence the requirement of metadata url.

```
def get_component_service(connector):
    stub_config = StubConfigurationFactory.new_std_configuration(connector)
    component_svc = metamodel_client.Component(stub_config)
    return component_svc
```

Once the connector which commuincates to vAPI provider is created, then it used by ```get_component_service()``` to create a stub configuration object. Stub config factory class create a stub configuration using the specified connection, with all the standard errors registered. This object acts as a Configuration data object for vAPI stub classes.

The component_svc object created by Component class of metamodel_client provides a method to retrieve metamodel information of a component element. A component defines a set of functionality that is deployed together & versioned together example: All the Library that belong to VMware content Library are part of a single component. This object inherits VapiInterface which is used by python client side binding that encapsulates the Api Interface Stub, Providing it the functionlity to invoke the connector to request for specific Vapi infrastructure related informations.

<explain more>

## Part - 3
```
def populate_dicts(component_svc, enumeration_dict, structure_dict, service_dict, service_urls_map, base_url):
    components = component_svc.list()
    
    for component in components:
        
        component_data = component_svc.get(component)
        component_packages = component_data.info.packages

        for package in component_packages:
            package_info = component_packages.get(package)
            for enumeration, enumeration_info in package_info.enumerations.items():
                enumeration_dict[enumeration] = enumeration_info

            for structure, structure_info in package_info.structures.items():
                structure_dict[structure] = structure_info
                for enum_name, enum_info in structure_info.enumerations.items():
                    enumeration_dict[enum_name] = enum_info

            for service, service_info in package_info.services.items():
                service_dict[service] = service_info
                service_urls_map[get_service_url_from_service_id(base_url, service)] = service
                for structure_name, structure_info in service_info.structures.items():
                    structure_dict[structure_name] = structure_info
                    for et1, et_info1 in structure_info.enumerations.items():
                        enumeration_dict[et1] = et_info1

                for enum_name, enum_info in service_info.enumerations.items():
                    enumeration_dict[enum_name] = enum_info
```
```component_svc.list()``` returns a list of identifiers of all the component elements that are registered with the infrastructure. Then we can loop through each component id provided and call the ```component_svc.get()``` function for a given component which will avail us to retrieve metamodel information about that component's elements. The returned object of  `ComponentData` contains the metamodel information about all the package element that are contained in the component elements. Now we fill the four data structures which were intialised in part 1 that are enumeration_dict, structure_dict, service_dict, service_urls_map.

## Part - 4
```
def get_service_urls_from_rest_navigation(rest_navigation_url, verify):
    component_services_urls = get_component_services_urls(rest_navigation_url, verify)
    return get_all_services_urls(component_services_urls, verify)
```

```get_service_urls_from_rest_navigation()``` takes in base url and makes a get request at /rest end point (.i.e https://\<vCenter ip\>/rest). This provides a json response with two main attributes `components` and `resources`, they both have a key named `href` whose value provides a link where we can find list of all the components (href: https://\<vCenter ip\>/rest/com/vmware/vapi/rest/navigation/component) and resources (href: https://\<vCenter ip\>/rest/com/vmware/vapi/rest/navigation/resource) urls. `get_component_services_urls()` is responsible of using component's href link to get a list of urls of all the components.
Each of this url provides a list of all the services supported by them and using this we create a dict named service_urls_map which holds { href:name } key value pair of each service across its corresponding componets, this is done by `get_all_services_urls()`.

In service_urls_map, key is a hyperlink with base template of https://\<vCenter ip\>/rest/com/vmware/\< package name \>/\< service path \>. `categorize_service_urls_by_package_names` extracts this package name and creates a dict of sturcture { \<package name\> : [ \< service url \>]}. `build_error_map()` provides a dict which maps vapi errors to http status codes.

## Part - 5

In this section multithreading is uitilised to process each package independently of others to convert it to openapi specification.

```
def process_service_urls(package_name, service_urls, output_dir, structure_dict, enum_dict, service_dict, service_url_dict, error_map, base_url):

    type_dict = {}
    path_list = []

    ## PART - 5.1
    for service_url in service_urls:

        
        service_name = service_url_dict.get(service_url, None)
        service_info = service_dict.get(service_name, None)
        if service_info is None:
            continue

        ## PART - 5.1.1
        if contains_rm_annotation(service_info):
            for operation in service_info.operations.values():
                url, method = find_url_method(operation)
                operation_id = operation.name
                operation_info = service_info.operations.get(operation_id)

                path = get_path(operation_info, method, url, service_name, type_dict, structure_dict, enum_dict,
                                operation_id, error_map)
                path_list.append(path)
            continue

        ## PART - 5.1.2
        # use rest navigation service to get the REST mappings for a service.
        service_operations = get_json(service_url + '?~method=OPTIONS', False)
        if service_operations is None:
            continue

        for service_operation in service_operations:
            service_name = service_operation['service']
            service_info = service_dict.get(service_name, None)
            if service_info is None:
                continue
            operation_id = service_operation['name']
            if operation_id not in service_info.operations:
                continue
            url, method = find_url(service_operation['links'])
            url = get_service_path_from_service_url(url, base_url)
            operation_info = service_info.operations.get(operation_id)
            path = get_path(operation_info, method, url, service_name, type_dict, structure_dict, enum_dict,
                            operation_id, error_map)
            path_list.append(path)
    
    ## PART - 5.2    
    path_dict = convert_path_list_to_path_map(path_list)
    cleanup(path_dict=path_dict, type_dict=type_dict)
    
    ## PART - 5.3
    process_output(path_dict, type_dict, output_dir, package_name)
```

### Part - 5.1
`service_urls` is list of services provided by the package, these urls can be used to get the metamodel information about all the package element from `service_url_dict`. 

This section is divided into two, first is in which swagger based path spec is created for service url which comes with request mapping but latter is for older version of vmodl2 files, one desgined when rest end points were not in a plan. Hence given their special case request mapping is produced by making a get request to service url with query parameter `method` set to `OPTIONS`.

#### Part - 5.1.1

service info object contains following attribute:
```
{
    name: name of the service, example: 'com.vmware.cis.session'
    operations: a map data sturcture, which contains operation's information aganist corresponding name of the operation. example: { 'get' : OperationInfo(...)}
    structures: structure are descritpion of complex object which define request and response body. This field contains map of all structures assocaited with the service, mapping the name of structure to that of structure information. Structure info object contains a important attribute called fields which is list of FieldInfo object that helps define this structures.
    enumerations: 
    constants: 
    metadata:
    documentation: 
    _extra_fields:
    _struct_value: 
    _rest_converter_mode:
}
```
`contains_rm_annotation` this function checks if all operation's metadata under a service contains details about request mapping, that is details about method type, url to request and query parameters are available or not. If request mapping exists then, then `find_url_method` is used to extract url with query parameter attached to it if any and type of request method that can be performed on the url.

`get_path` is the most important function which takes in operations info and builds swagger based path spec, it is also common in section of 5.1.1 and 5.1.2 for the same purpose.

```
def get_path(operation_info, http_method, url, service_name, type_dict, structure_dict, enum_dict,
             operation_id, error_map):
    documentation = operation_info.documentation
    params = operation_info.params
    errors = operation_info.errors
    output = operation_info.output
    http_method = http_method.lower()
    consumes_json = find_consumes(http_method)
    produces = None
    par_array, url = handle_request_mapping(url, http_method, service_name,
                                            operation_id, params, type_dict,
                                            structure_dict, enum_dict)
    response_map = populate_response_map(output,
                                         errors,
                                         error_map, type_dict, structure_dict, enum_dict, service_name, operation_id)

    path = build_path(service_name,
                      http_method,
                      url,
                      documentation, par_array, operation_id=operation_id,
                      responses=response_map,
                      consumes=consumes_json, produces=produces)
    return path
```

`get_path` function usees operation info object to extract following details to build swagger path .i.e documentation, params, errors, output and possible http methods. `find_consumes` function is used to determine mediaType for input parameters in a request body i.e for other then `get` & `delete` media type is set to `application/json`.

`handle_request_mapping`