//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ContainerInfoItem {
  /// Returns a new [ContainerInfoItem] instance.
  ContainerInfoItem({
    required this.created,
    required this.image,
    required this.name,
    required this.ports,
    required this.status,
  });

  String created;

  String image;

  String name;

  String ports;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ContainerInfoItem &&
    other.created == created &&
    other.image == image &&
    other.name == name &&
    other.ports == ports &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (created.hashCode) +
    (image.hashCode) +
    (name.hashCode) +
    (ports.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'ContainerInfoItem[created=$created, image=$image, name=$name, ports=$ports, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'created'] = this.created;
      json[r'image'] = this.image;
      json[r'name'] = this.name;
      json[r'ports'] = this.ports;
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [ContainerInfoItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ContainerInfoItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ContainerInfoItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ContainerInfoItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ContainerInfoItem(
        created: mapValueOfType<String>(json, r'created')!,
        image: mapValueOfType<String>(json, r'image')!,
        name: mapValueOfType<String>(json, r'name')!,
        ports: mapValueOfType<String>(json, r'ports')!,
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<ContainerInfoItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ContainerInfoItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ContainerInfoItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ContainerInfoItem> mapFromJson(dynamic json) {
    final map = <String, ContainerInfoItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ContainerInfoItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ContainerInfoItem-objects as value to a dart map
  static Map<String, List<ContainerInfoItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ContainerInfoItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ContainerInfoItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'created',
    'image',
    'name',
    'ports',
    'status',
  };
}

