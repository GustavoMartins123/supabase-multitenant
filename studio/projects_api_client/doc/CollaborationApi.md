# projects_api_client.api.CollaborationApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**assignProjectTagApiProjectsProjectNameTagsPost**](CollaborationApi.md#assignprojecttagapiprojectsprojectnametagspost) | **POST** /api/projects/{project_name}/tags | Assign Project Tag
[**createProjectHintApiProjectsProjectNameHintsPost**](CollaborationApi.md#createprojecthintapiprojectsprojectnamehintspost) | **POST** /api/projects/{project_name}/hints | Create Project Hint
[**createProjectNoteApiProjectsProjectNameNotesPost**](CollaborationApi.md#createprojectnoteapiprojectsprojectnamenotespost) | **POST** /api/projects/{project_name}/notes | Create Project Note
[**createProjectThreadMessageApiProjectsProjectNameThreadMessagesPost**](CollaborationApi.md#createprojectthreadmessageapiprojectsprojectnamethreadmessagespost) | **POST** /api/projects/{project_name}/thread/messages | Create Project Thread Message
[**deleteProjectNoteApiProjectsProjectNameNotesNoteIdDelete**](CollaborationApi.md#deleteprojectnoteapiprojectsprojectnamenotesnoteiddelete) | **DELETE** /api/projects/{project_name}/notes/{note_id} | Delete Project Note
[**getProjectCollaborationApiProjectsProjectNameCollaborationGet**](CollaborationApi.md#getprojectcollaborationapiprojectsprojectnamecollaborationget) | **GET** /api/projects/{project_name}/collaboration | Get Project Collaboration
[**unassignProjectTagApiProjectsProjectNameTagsTagIdDelete**](CollaborationApi.md#unassignprojecttagapiprojectsprojectnametagstagiddelete) | **DELETE** /api/projects/{project_name}/tags/{tag_id} | Unassign Project Tag
[**updateProjectHintStatusApiProjectsProjectNameHintsHintIdPut**](CollaborationApi.md#updateprojecthintstatusapiprojectsprojectnamehintshintidput) | **PUT** /api/projects/{project_name}/hints/{hint_id} | Update Project Hint Status
[**updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatch**](CollaborationApi.md#updateprojectnotificationreadstateapiprojectsprojectnamenotificationsnotificationidpatch) | **PATCH** /api/projects/{project_name}/notifications/{notification_id} | Update Project Notification Read State


# **assignProjectTagApiProjectsProjectNameTagsPost**
> AssignProjectTagResponse assignProjectTagApiProjectsProjectNameTagsPost(projectName, projectTagAssign)

Assign Project Tag

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final projectTagAssign = ProjectTagAssign(); // ProjectTagAssign | 

try {
    final result = api_instance.assignProjectTagApiProjectsProjectNameTagsPost(projectName, projectTagAssign);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->assignProjectTagApiProjectsProjectNameTagsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **projectTagAssign** | [**ProjectTagAssign**](ProjectTagAssign.md)|  | 

### Return type

[**AssignProjectTagResponse**](AssignProjectTagResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createProjectHintApiProjectsProjectNameHintsPost**
> CreateProjectHintResponse createProjectHintApiProjectsProjectNameHintsPost(projectName, projectHintCreate)

Create Project Hint

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final projectHintCreate = ProjectHintCreate(); // ProjectHintCreate | 

try {
    final result = api_instance.createProjectHintApiProjectsProjectNameHintsPost(projectName, projectHintCreate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->createProjectHintApiProjectsProjectNameHintsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **projectHintCreate** | [**ProjectHintCreate**](ProjectHintCreate.md)|  | 

### Return type

[**CreateProjectHintResponse**](CreateProjectHintResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createProjectNoteApiProjectsProjectNameNotesPost**
> CreateProjectNoteResponse createProjectNoteApiProjectsProjectNameNotesPost(projectName, projectNoteCreate)

Create Project Note

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final projectNoteCreate = ProjectNoteCreate(); // ProjectNoteCreate | 

try {
    final result = api_instance.createProjectNoteApiProjectsProjectNameNotesPost(projectName, projectNoteCreate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->createProjectNoteApiProjectsProjectNameNotesPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **projectNoteCreate** | [**ProjectNoteCreate**](ProjectNoteCreate.md)|  | 

### Return type

[**CreateProjectNoteResponse**](CreateProjectNoteResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createProjectThreadMessageApiProjectsProjectNameThreadMessagesPost**
> CreateThreadMessageResponse createProjectThreadMessageApiProjectsProjectNameThreadMessagesPost(projectName, projectThreadMessageCreate)

Create Project Thread Message

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final projectThreadMessageCreate = ProjectThreadMessageCreate(); // ProjectThreadMessageCreate | 

try {
    final result = api_instance.createProjectThreadMessageApiProjectsProjectNameThreadMessagesPost(projectName, projectThreadMessageCreate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->createProjectThreadMessageApiProjectsProjectNameThreadMessagesPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **projectThreadMessageCreate** | [**ProjectThreadMessageCreate**](ProjectThreadMessageCreate.md)|  | 

### Return type

[**CreateThreadMessageResponse**](CreateThreadMessageResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **deleteProjectNoteApiProjectsProjectNameNotesNoteIdDelete**
> DeleteProjectNoteResponse deleteProjectNoteApiProjectsProjectNameNotesNoteIdDelete(projectName, noteId)

Delete Project Note

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final noteId = noteId_example; // String | 

try {
    final result = api_instance.deleteProjectNoteApiProjectsProjectNameNotesNoteIdDelete(projectName, noteId);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->deleteProjectNoteApiProjectsProjectNameNotesNoteIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **noteId** | **String**|  | 

### Return type

[**DeleteProjectNoteResponse**](DeleteProjectNoteResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectCollaborationApiProjectsProjectNameCollaborationGet**
> GetProjectCollaborationResponse getProjectCollaborationApiProjectsProjectNameCollaborationGet(projectName)

Get Project Collaboration

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getProjectCollaborationApiProjectsProjectNameCollaborationGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->getProjectCollaborationApiProjectsProjectNameCollaborationGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 

### Return type

[**GetProjectCollaborationResponse**](GetProjectCollaborationResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **unassignProjectTagApiProjectsProjectNameTagsTagIdDelete**
> UnassignProjectTagResponse unassignProjectTagApiProjectsProjectNameTagsTagIdDelete(projectName, tagId)

Unassign Project Tag

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final tagId = tagId_example; // String | 

try {
    final result = api_instance.unassignProjectTagApiProjectsProjectNameTagsTagIdDelete(projectName, tagId);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->unassignProjectTagApiProjectsProjectNameTagsTagIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **tagId** | **String**|  | 

### Return type

[**UnassignProjectTagResponse**](UnassignProjectTagResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProjectHintStatusApiProjectsProjectNameHintsHintIdPut**
> UpdateProjectHintResponse updateProjectHintStatusApiProjectsProjectNameHintsHintIdPut(projectName, hintId, projectHintStatusUpdate)

Update Project Hint Status

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final hintId = hintId_example; // String | 
final projectHintStatusUpdate = ProjectHintStatusUpdate(); // ProjectHintStatusUpdate | 

try {
    final result = api_instance.updateProjectHintStatusApiProjectsProjectNameHintsHintIdPut(projectName, hintId, projectHintStatusUpdate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->updateProjectHintStatusApiProjectsProjectNameHintsHintIdPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **hintId** | **String**|  | 
 **projectHintStatusUpdate** | [**ProjectHintStatusUpdate**](ProjectHintStatusUpdate.md)|  | 

### Return type

[**UpdateProjectHintResponse**](UpdateProjectHintResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatch**
> UpdateNotificationReadResponse updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatch(projectName, notificationId, projectNotificationRead)

Update Project Notification Read State

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectName = projectName_example; // String | 
final notificationId = notificationId_example; // String | 
final projectNotificationRead = ProjectNotificationRead(); // ProjectNotificationRead | 

try {
    final result = api_instance.updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatch(projectName, notificationId, projectNotificationRead);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **notificationId** | **String**|  | 
 **projectNotificationRead** | [**ProjectNotificationRead**](ProjectNotificationRead.md)|  | 

### Return type

[**UpdateNotificationReadResponse**](UpdateNotificationReadResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

