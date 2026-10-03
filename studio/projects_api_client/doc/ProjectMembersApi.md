# projects_api_client.api.ProjectMembersApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**addMemberApiProjectsProjectRefMembersPost**](ProjectMembersApi.md#addmemberapiprojectsprojectrefmemberspost) | **POST** /api/projects/{project_ref}/members | Add Member
[**listMembersByRefApiProjectsProjectRefMembersGet**](ProjectMembersApi.md#listmembersbyrefapiprojectsprojectrefmembersget) | **GET** /api/projects/{project_ref}/members | List Members By Ref
[**removeMemberByRefApiProjectsProjectRefMembersMemberIdDelete**](ProjectMembersApi.md#removememberbyrefapiprojectsprojectrefmembersmemberiddelete) | **DELETE** /api/projects/{project_ref}/members/{member_id} | Remove Member By Ref


# **addMemberApiProjectsProjectRefMembersPost**
> AddMemberResponse addMemberApiProjectsProjectRefMembersPost(projectRef, addMember)

Add Member

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectMembersApi();
final projectRef = projectRef_example; // String |
final addMember = AddMember(); // AddMember | 

try {
    final result = api_instance.addMemberApiProjectsProjectRefMembersPost(projectRef, addMember);
    print(result);
} catch (e) {
    print('Exception when calling ProjectMembersApi->addMemberApiProjectsProjectRefMembersPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **addMember** | [**AddMember**](AddMember.md)|  | 

### Return type

[**AddMemberResponse**](AddMemberResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listMembersByRefApiProjectsProjectRefMembersGet**
> List<MemberItem> listMembersByRefApiProjectsProjectRefMembersGet(projectRef)

List Members By Ref

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectMembersApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.listMembersByRefApiProjectsProjectRefMembersGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling ProjectMembersApi->listMembersByRefApiProjectsProjectRefMembersGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**List<MemberItem>**](MemberItem.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **removeMemberByRefApiProjectsProjectRefMembersMemberIdDelete**
> RemoveMemberResponse removeMemberByRefApiProjectsProjectRefMembersMemberIdDelete(projectRef, memberId)

Remove Member By Ref

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectMembersApi();
final projectRef = projectRef_example; // String |
final memberId = memberId_example; // String | 

try {
    final result = api_instance.removeMemberByRefApiProjectsProjectRefMembersMemberIdDelete(projectRef, memberId);
    print(result);
} catch (e) {
    print('Exception when calling ProjectMembersApi->removeMemberByRefApiProjectsProjectRefMembersMemberIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **memberId** | **String**|  | 

### Return type

[**RemoveMemberResponse**](RemoveMemberResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

