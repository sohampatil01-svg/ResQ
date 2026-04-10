# ResQ Android Wrapper

This is an Android Studio wrapper app for the ResQ web application.

## What it does
- Loads the ResQ web UI in an Android `WebView`
- Enables JavaScript, geolocation, and file upload support
- Allows setting the backend URL for emulator (`http://10.0.2.2:8000`) or device access (`http://<PC_IP>:8000`)
- Supports cleartext HTTP traffic via network security config

## Open in Android Studio
1. Open Android Studio
2. Select `Open` and choose `d:\hack\android-app`
3. Sync Gradle
4. Run the `app` module on an emulator or connected device

## Server URL
- Default emulator URL: `http://10.0.2.2:8000`
- Use the menu button to change the URL to your PC IP if running on a real device:
  - `http://192.168.x.x:8000`

## Notes
- Start the ResQ backend before opening the app
- If Android Studio prompts for a Gradle wrapper, allow it to use a local Gradle installation or generate the wrapper
