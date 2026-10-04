# projects_api_client.api.CollaborationApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**assignProjectTagApiProjectsProjectRefTagsPost**](CollaborationApi.md#assignprojecttagapiprojectsprojectreftagspost) | **POST** /api/projects/{project_ref}/tags | Assign Project Tag
[**createProjectHintApiProjectsProjectRefHintsPost**](CollaborationApi.md#createprojecthintapiprojectsprojectrefhintspost) | **POST** /api/projects/{project_ref}/hints | Create Project Hint
[**createProjectNoteApiProjectsProjectRefNotesPost**](CollaborationApi.md#createprojectnoteapiprojectsprojectrefnotespost) | **POST** /api/projects/{project_ref}/notes | Create Project Note
[**createProjectThreadMessageApiProjectsProjectRefThreadMessagesPost**](CollaborationApi.md#createprojectthreadmessageapiprojectsprojectrefthreadmessagespost) | **POST** /api/projects/{project_ref}/thread/messages | Create Project Thread Message
[**deleteProjectNoteApiProjectsProjectRefNotesNoteIdDelete**](CollaborationApi.md#deleteprojectnoteapiprojectsprojectrefnotesnoteiddelete) | **DELETE** /api/projects/{project_ref}/notes/{note_id} | Delete Project Note
[**getProjectCollaborationApiProjectsProjectRefCollaborationGet**](CollaborationApi.md#getprojectcollaborationapiprojectsprojectrefcollaborationget) | **GET** /api/projects/{project_ref}/collaboration | Get Project Collaboration
[**unassignProjectTagApiProjectsProjectRefTagsTagIdDelete**](CollaborationApi.md#unassignprojecttagapiprojectsprojectreftagstagiddelete) | **DELETE** /api/projects/{project_ref}/tags/{tag_id} | Unassign Project Tag
[**updateProjectHintStatusApiProjectsProjectRefHintsHintIdPut**](CollaborationApi.md#updateprojecthintstatusapiprojectsprojectrefhintshintidput) | **PUT** /api/projects/{project_ref}/hints/{hint_id} | Update Project Hint Status
[**updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatch**](CollaborationApi.md#updateprojectnotificationreadstateapiprojectsprojectrefnotificationsnotificationidpatch) | **PATCH** /api/projects/{project_ref}/notifications/{notification_id} | Update Project Notification Read State


# **assignProjectTagApiProjectsProjectRefTagsPost**
> AssignProjectTagResponse assignProjectTagApiProjectsProjectRefTagsPost(projectRef, projectTagAssign)

Assign Project Tag

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final projectTagAssign = ProjectTagAssign(); // ProjectTagAssign |

try {
    final result = api_instance.assignProjectTagApiProjectsProjectRefTagsPost(projectRef, projectTagAssign);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->assignProjectTagApiProjectsProjectRefTagsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **projectTagAssign** | [**ProjectTagAssign**](ProjectTagAssign.md)|  |

### Return type

[**AssignProjectTagResponse**](AssignProjectTagResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createProjectHintApiProjectsProjectRefHintsPost**
> CreateProjectHintResponse createProjectHintApiProjectsProjectRefHintsPost(projectRef, projectHintCreate)

Create Project Hint

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final projectHintCreate = ProjectHintCreate(); // ProjectHintCreate |

try {
    final result = api_instance.createProjectHintApiProjectsProjectRefHintsPost(projectRef, projectHintCreate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->createProjectHintApiProjectsProjectRefHintsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **projectHintCreate** | [**ProjectHintCreate**](ProjectHintCreate.md)|  |

### Return type

[**CreateProjectHintResponse**](CreateProjectHintResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createProjectNoteApiProjectsProjectRefNotesPost**
> CreateProjectNoteResponse createProjectNoteApiProjectsProjectRefNotesPost(projectRef, projectNoteCreate)

Create Project Note

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final projectNoteCreate = ProjectNoteCreate(); // ProjectNoteCreate |

try {
    final result = api_instance.createProjectNoteApiProjectsProjectRefNotesPost(projectRef, projectNoteCreate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->createProjectNoteApiProjectsProjectRefNotesPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **projectNoteCreate** | [**ProjectNoteCreate**](ProjectNoteCreate.md)|  |

### Return type

[**CreateProjectNoteResponse**](CreateProjectNoteResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createProjectThreadMessageApiProjectsProjectRefThreadMessagesPost**
> CreateThreadMessageResponse createProjectThreadMessageApiProjectsProjectRefThreadMessagesPost(projectRef, projectThreadMessageCreate)

Create Project Thread Message

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final projectThreadMessageCreate = ProjectThreadMessageCreate(); // ProjectThreadMessageCreate |

try {
    final result = api_instance.createProjectThreadMessageApiProjectsProjectRefThreadMessagesPost(projectRef, projectThreadMessageCreate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->createProjectThreadMessageApiProjectsProjectRefThreadMessagesPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **projectThreadMessageCreate** | [**ProjectThreadMessageCreate**](ProjectThreadMessageCreate.md)|  |

### Return type

[**CreateThreadMessageResponse**](CreateThreadMessageResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **deleteProjectNoteApiProjectsProjectRefNotesNoteIdDelete**
> DeleteProjectNoteResponse deleteProjectNoteApiProjectsProjectRefNotesNoteIdDelete(projectRef, noteId)

Delete Project Note

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final noteId = noteId_example; // String |

try {
    final result = api_instance.deleteProjectNoteApiProjectsProjectRefNotesNoteIdDelete(projectRef, noteId);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->deleteProjectNoteApiProjectsProjectRefNotesNoteIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **noteId** | **String**|  |

### Return type

[**DeleteProjectNoteResponse**](DeleteProjectNoteResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectCollaborationApiProjectsProjectRefCollaborationGet**
> GetProjectCollaborationResponse getProjectCollaborationApiProjectsProjectRefCollaborationGet(projectRef)

Get Project Collaboration

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getProjectCollaborationApiProjectsProjectRefCollaborationGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->getProjectCollaborationApiProjectsProjectRefCollaborationGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**GetProjectCollaborationResponse**](GetProjectCollaborationResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **unassignProjectTagApiProjectsProjectRefTagsTagIdDelete**
> UnassignProjectTagResponse unassignProjectTagApiProjectsProjectRefTagsTagIdDelete(projectRef, tagId)

Unassign Project Tag

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final tagId = tagId_example; // String |

try {
    final result = api_instance.unassignProjectTagApiProjectsProjectRefTagsTagIdDelete(projectRef, tagId);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->unassignProjectTagApiProjectsProjectRefTagsTagIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **tagId** | **String**|  |

### Return type

[**UnassignProjectTagResponse**](UnassignProjectTagResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProjectHintStatusApiProjectsProjectRefHintsHintIdPut**
> UpdateProjectHintResponse updateProjectHintStatusApiProjectsProjectRefHintsHintIdPut(projectRef, hintId, projectHintStatusUpdate)

Update Project Hint Status

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final hintId = hintId_example; // String |
final projectHintStatusUpdate = ProjectHintStatusUpdate(); // ProjectHintStatusUpdate |

try {
    final result = api_instance.updateProjectHintStatusApiProjectsProjectRefHintsHintIdPut(projectRef, hintId, projectHintStatusUpdate);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->updateProjectHintStatusApiProjectsProjectRefHintsHintIdPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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

# **updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatch**
> UpdateNotificationReadResponse updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatch(projectRef, notificationId, projectNotificationRead)

Update Project Notification Read State

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = CollaborationApi();
final projectRef = projectRef_example; // String |
final notificationId = notificationId_example; // String |
final projectNotificationRead = ProjectNotificationRead(); // ProjectNotificationRead |

try {
    final result = api_instance.updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatch(projectRef, notificationId, projectNotificationRead);
    print(result);
} catch (e) {
    print('Exception when calling CollaborationApi->updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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

