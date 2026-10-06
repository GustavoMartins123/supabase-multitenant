#!/usr/bin/env bash

realtime_slot_hash() {
    printf '%s' "$1" | md5sum | cut -c1-8
}

realtime_slot_candidate() {
    local base="$1" project="$2" full keep
    full="${base}${project}"
    if [ "${#full}" -le 63 ]; then
        printf '%s\n' "$full"
        return 0
    fi
    keep=$(( 63 - ${#base} - 9 ))
    printf '%s\n' "${base}${project:0:keep}_$(realtime_slot_hash "$full")"
}

realtime_slot_candidates() {
    local project="$1"
    realtime_slot_candidate "supabase_realtime_messages_replication_slot_" "$project"
    printf '%s\n' "supabase_realtime_messages_replication_slot_${project:0:63}"
    realtime_slot_candidate "supabase_realtime_replication_slot_" "$project"
    printf '%s\n' "supabase_realtime_replication_slot_${project:0:63}"
}

realtime_slot_candidates_unique() {
    realtime_slot_candidates "$1" | awk '!seen[$0]++'
}

realtime_primary_slot() {
    realtime_slot_candidate "supabase_realtime_replication_slot_" "$1"
}
