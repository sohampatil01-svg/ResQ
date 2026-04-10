package com.resq.mobile

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.telephony.SmsManager
import android.util.Log
import android.webkit.*
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private val locationPermissionRequestCode = 1001

    companion object {
        @JvmStatic
        var instance: MainActivity? = null
            private set
    }

    private val fileChooserLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode != Activity.RESULT_OK || result.data == null) {
            fileChooserCallback?.onReceiveValue(null)
            fileChooserCallback = null
            return@registerForActivityResult
        }

        val data = result.data!!
        val results = when {
            data.clipData != null -> {
                val count = data.clipData!!.itemCount
                Array(count) { index -> data.clipData!!.getItemAt(index).uri }
            }
            data.data != null -> arrayOf(data.data!!)
            else -> null
        }

        fileChooserCallback?.onReceiveValue(results)
        fileChooserCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        instance = this
        setContentView(R.layout.activity_main)

        // Initialize Chaquopy Python
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // Start the Flask server in a background thread
        startFlaskServer()

        webView = findViewById(R.id.web_view)
        val toolbar = findViewById<androidx.appcompat.widget.Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        setupWebView()
        requestLocationPermissions()

        // Wait a moment for the server to start, then load the local server
        webView.postDelayed({
            loadUrl("http://127.0.0.1:8000")
        }, 2000) // 2 second delay
    }

    /**
     * Called from Python via Chaquopy to send a real SMS alert
     */
    fun sendSMS(phoneNumber: String, message: String) {
        runOnUiThread {
            try {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED) {
                    val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                        this.getSystemService(SmsManager::class.java)
                    } else {
                        @Suppress("DEPRECATION")
                        SmsManager.getDefault()
                    }

                    val sentIntent = PendingIntent.getBroadcast(
                        this, 0,
                        Intent(this, SmsSentReceiver::class.java),
                        PendingIntent.FLAG_IMMUTABLE
                    )

                    if (message.length > 160) {
                        val parts = smsManager.divideMessage(message)
                        val sentIntents = ArrayList<PendingIntent>(parts.size).also { list ->
                            repeat(parts.size) { list.add(sentIntent) }
                        }
                        smsManager.sendMultipartTextMessage(phoneNumber, null, parts, sentIntents, null)
                    } else {
                        smsManager.sendTextMessage(phoneNumber, null, message, sentIntent, null)
                    }
                    
                    Toast.makeText(this, "SOS Alert dispatched to $phoneNumber", Toast.LENGTH_SHORT).show()
                } else {
                    // Fallback to Intent if permission not granted
                    val intent = Intent(Intent.ACTION_SENDTO).apply {
                        data = Uri.parse("smsto:$phoneNumber")
                        putExtra("sms_body", message)
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    startActivity(intent)
                    Toast.makeText(this, "Grant SMS permission for automatic sending", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                e.printStackTrace()
                Toast.makeText(this, "Failed to send SMS: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun startFlaskServer() {
        Thread {
            try {
                val python = Python.getInstance()
                val mainModule = python.getModule("main")
                mainModule.callAttr("main")
                runOnUiThread {
                    Toast.makeText(this, "Flask server started successfully", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    Toast.makeText(this, "Failed to start server: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadsImagesAutomatically = true
            allowFileAccess = true
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
            databaseEnabled = true
            setGeolocationEnabled(true)
            setJavaScriptCanOpenWindowsAutomatically(true)
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                
                // If it's the local Flask server, allow it to load in WebView
                if (url.startsWith("http://127.0.0.1:8000") || url.startsWith("http://localhost:8000")) {
                    return false
                }
                
                // For everything else (Google Maps, tel, sms, external sites), use Intents
                try {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    startActivity(intent)
                    return true
                } catch (e: Exception) {
                    Log.e("WebView", "Error handling external URL: $url", e)
                    // If no app can handle it, just let WebView try (or fail gracefully)
                    return false
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onGeolocationPermissionsShowPrompt(origin: String, callback: GeolocationPermissions.Callback) {
                callback.invoke(origin, true, false)
            }

            override fun onPermissionRequest(request: PermissionRequest) {
                request.grant(request.resources)
            }

            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                val intent = fileChooserParams.createIntent()
                return try {
                    fileChooserLauncher.launch(intent)
                    true
                } catch (e: ActivityNotFoundException) {
                    fileChooserCallback = null
                    Toast.makeText(this@MainActivity, getString(R.string.file_picker_error), Toast.LENGTH_SHORT).show()
                    false
                }
            }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)
        } else {
            CookieManager.getInstance().setAcceptCookie(true)
        }
    }

    private fun loadUrl(url: String) {
        val normalized = if (url.endsWith("/")) url else "$url/"
        webView.loadUrl(normalized)
        title = getString(R.string.app_name)
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onCreateOptionsMenu(menu: android.view.Menu): Boolean {
        menuInflater.inflate(R.menu.menu_main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: android.view.MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_refresh -> {
                webView.reload()
                true
            }
            R.id.action_url -> {
                showUrlDialog()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun showUrlDialog() {
        val prefs = getSharedPreferences("resq_prefs", MODE_PRIVATE)
        val current = prefs.getString("resq_url", "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000"
        val editText = EditText(this).apply {
            setText(current)
            setSingleLine(true)
            hint = getString(R.string.url_hint)
        }

        AlertDialog.Builder(this)
            .setTitle(R.string.change_url)
            .setView(editText)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val newUrl = editText.text.toString().trim()
                if (newUrl.isNotEmpty()) {
                    prefs.edit().putString("resq_url", newUrl).apply()
                    loadUrl(newUrl)
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun requestLocationPermissions() {
        val missing = locationPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), locationPermissionRequestCode)
        }
    }

    private fun locationPermissions() = listOf(
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION,
        Manifest.permission.SEND_SMS
    )

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == locationPermissionRequestCode) {
            if (grantResults.any { it == PackageManager.PERMISSION_GRANTED }) {
                webView.reload()
            }
        }
    }
}

class SmsSentReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (resultCode) {
            Activity.RESULT_OK ->
                Log.d("SmsSent", "SOS SMS sent successfully")
            SmsManager.RESULT_ERROR_GENERIC_FAILURE ->
                Log.e("SmsSent", "SMS failed: generic failure")
            SmsManager.RESULT_ERROR_NO_SERVICE ->
                Log.e("SmsSent", "SMS failed: no service")
            SmsManager.RESULT_ERROR_NULL_PDU ->
                Log.e("SmsSent", "SMS failed: null PDU")
            SmsManager.RESULT_ERROR_RADIO_OFF ->
                Log.e("SmsSent", "SMS failed: radio off")
        }
    }
}
