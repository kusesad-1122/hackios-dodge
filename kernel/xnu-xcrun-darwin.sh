#!/bin/bash
# XNU reads headers and archives from a local SDK overlay. Xcode's metadata
# and tool lookup must still use its registered iPhoneOS SDK.
set -euo pipefail
args=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        -sdk|--sdk)
            [ "$#" -ge 2 ] || { echo "xcrun: missing SDK argument" >&2; exit 2; }
            sdk=$2
            if [ -n "${XNU_SDK_PATH:-}" ] && [ "$sdk" = "$XNU_SDK_PATH" ]; then
                sdk=iphoneos
            fi
            args+=("$1" "$sdk")
            shift 2
            ;;
        *) args+=("$1"); shift ;;
    esac
done
exec /usr/bin/xcrun "${args[@]}"
