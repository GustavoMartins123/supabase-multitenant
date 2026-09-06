# projects_api_client.api.ProjectMembersApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**addMemberApiProjectsProjectNameMembersPost**](ProjectMembersApi.md#addmemberapiprojectsprojectnamememberspost) | **POST** /api/projects/{project_name}/members | Add Member
[**listMembersByRefApiProjectsNameMembersGet**](ProjectMembersApi.md#listmembersbyrefapiprojectsnamemembersget) | **GET** /api/projects/{name}/members | List Members By Ref
[**removeMemberByRefApiProjectsNameMembersMemberIdDelete**](ProjectMembersApi.md#removememberbyrefapiprojectsnamemembersmemberiddelete) | **DELETE** /api/projects/{name}/members/{member_id} | Remove Member By Ref


# **addMemberApiProjectsProjectNameMembersPost**
> AddMemberResponse addMemberApiProjectsProjectNameMembersPost(projectName, addMember)

Add Member

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectMembersApi();
final projectName = projectName_example; // String | 
final addMember = AddMember(); // AddMember | 

try {
    final result = api_instance.addMemberApiProjectsProjectNameMembersPost(projectName, addMember);
    print(result);
} catch (e) {
    print('Exception when calling ProjectMembersApi->addMemberApiProjectsProjectNameMembersPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **addMember** | [**AddMember**](AddMember.md)|  | 

### Return type

[**AddMemberResponse**](AddMemberResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listMembersByRefApiProjectsNameMembersGet**
> List<MemberItem> listMembersByRefApiProjectsNameMembersGet(name)

List Members By Ref

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectMembersApi();
final name = name_example; // String | 

try {
    final result = api_instance.listMembersByRefApiProjectsNameMembersGet(name);
    print(result);
} catch (e) {
    print('Exception when calling ProjectMembersApi->listMembersByRefApiProjectsNameMembersGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **String**|  | 

### Return type

[**List<MemberItem>**](MemberItem.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **removeMemberByRefApiProjectsNameMembersMemberIdDelete**
> RemoveMemberResponse removeMemberByRefApiProjectsNameMembersMemberIdDelete(name, memberId)

Remove Member By Ref

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectMembersApi();
final name = name_example; // String | 
final memberId = memberId_example; // String | 

try {
    final result = api_instance.removeMemberByRefApiProjectsNameMembersMemberIdDelete(name, memberId);
    print(result);
} catch (e) {
    print('Exception when calling ProjectMembersApi->removeMemberByRefApiProjectsNameMembersMemberIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **String**|  | 
 **memberId** | **String**|  | 

### Return type

[**RemoveMemberResponse**](RemoveMemberResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

