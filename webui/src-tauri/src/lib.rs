use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[cfg(unix)]
use std::os::unix::process::CommandExt;

use tauri::menu::{AboutMetadata, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{Emitter, Listener, Manager, Wry};
use tauri::WindowEvent;

#[derive(Clone)]
struct BackendChild(Arc<Mutex<Option<Child>>>);

#[derive(Clone)]
struct ApiBase(String);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .menu(|handle| {
      let about_metadata = build_about_metadata();
      let prefs = MenuItem::with_id(handle, "preferences", "Preferences\u{2026}", true, Some("Cmd+,"));
      let app_menu = Submenu::with_items(
        handle,
        "Easy",
        true,
        &[
          &PredefinedMenuItem::about(handle, None, Some(about_metadata))?,
          &PredefinedMenuItem::separator(handle)?,
          &prefs?,
          &PredefinedMenuItem::separator(handle)?,
          &PredefinedMenuItem::quit(handle, None)?,
        ],
      )?;
      Menu::with_items(handle, &[&app_menu])
    })
    .on_menu_event(|app, event| {
      let open_settings_window = |app: &tauri::AppHandle<Wry>| {
        let api_base = app.state::<ApiBase>().0.clone();
        if app.get_webview_window("settings").is_none() {
          match tauri::WebviewWindowBuilder::new(
            app,
            "settings",
            tauri::WebviewUrl::App("index.html?window=settings".into()),
          )
          .title("Settings")
          .inner_size(500.0, 370.0)
          .resizable(false)
          .title_bar_style(tauri::TitleBarStyle::Overlay)
          .hidden_title(true)
          .build()
          {
            Ok(window) => {
              let script = format!(
                "window.__EASY_API_BASE__ = \"{api_base}\"; \
                 window.dispatchEvent(new CustomEvent('easy://api-base', {{ detail: \"{api_base}\" }}));"
              );
              let _ = window.eval(&script);
              println!("[easy][tauri] settings window created");
            }
            Err(err) => println!("[easy][tauri] settings window error: {err}"),
          }
        } else if let Some(window) = app.get_webview_window("settings") {
          let script = format!(
            "window.__EASY_API_BASE__ = \"{api_base}\"; \
             window.dispatchEvent(new CustomEvent('easy://api-base', {{ detail: \"{api_base}\" }}));"
          );
          let _ = window.eval(&script);
          let _ = window.show();
          let _ = window.set_focus();
          println!("[easy][tauri] settings window focused");
        }
      };
      if event.id() == "preferences" {
        println!("[easy][tauri] preferences menu clicked");
        open_settings_window(app.app_handle());
      }
    })
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      let (api_base, child) = spawn_backend(app)?;
      app.manage(BackendChild(Arc::new(Mutex::new(Some(child)))));
      app.manage(ApiBase(api_base.clone()));
      app.emit("easy://api-base", api_base.clone())?;

      let app_handle = app.handle().clone();
      let app_handle_for_event = app_handle.clone();
      app_handle.listen("easy://frontend-ready", move |_| {
        println!("[easy][tauri] frontend-ready received");
        if let Some(window) = app_handle_for_event.get_webview_window("main") {
          let _ = window.show();
          let _ = window.set_focus();
        }
      });

      let app_handle_for_settings = app.handle().clone();
      app_handle.listen("easy://open-settings-window", move |_| {
        let api_base = app_handle_for_settings.state::<ApiBase>().0.clone();
        if app_handle_for_settings.get_webview_window("settings").is_none() {
          match tauri::WebviewWindowBuilder::new(
            &app_handle_for_settings,
            "settings",
            tauri::WebviewUrl::App("index.html?window=settings".into()),
          )
          .title("Settings")
          .inner_size(500.0, 370.0)
          .resizable(false)
          .title_bar_style(tauri::TitleBarStyle::Overlay)
          .hidden_title(true)
          .build()
          {
            Ok(window) => {
              let script = format!(
                "window.__EASY_API_BASE__ = \"{api_base}\"; \
                 window.dispatchEvent(new CustomEvent('easy://api-base', {{ detail: \"{api_base}\" }}));"
              );
              let _ = window.eval(&script);
              println!("[easy][tauri] settings window created (event)");
            }
            Err(err) => println!("[easy][tauri] settings window error (event): {err}"),
          }
        } else if let Some(window) = app_handle_for_settings.get_webview_window("settings") {
          let script = format!(
            "window.__EASY_API_BASE__ = \"{api_base}\"; \
             window.dispatchEvent(new CustomEvent('easy://api-base', {{ detail: \"{api_base}\" }}));"
          );
          let _ = window.eval(&script);
          let _ = window.show();
          let _ = window.set_focus();
          println!("[easy][tauri] settings window focused (event)");
        }
      });

      if let Some(window) = app.get_webview_window("main") {
        let script = format!(
          "window.__EASY_API_BASE__ = \"{api_base}\"; \
           window.dispatchEvent(new CustomEvent('easy://api-base', {{ detail: \"{api_base}\" }}));"
        );
        let _ = window.eval(&script);
      }

      Ok(())
    })
    .on_window_event(|window, event| {
      if let WindowEvent::CloseRequested { .. } = event {
        if window.label() == "main" {
          let app_handle = window.app_handle();
          for (label, other) in app_handle.webview_windows() {
            if label != "main" {
              let _ = other.close();
            }
          }
          shutdown_backend(app_handle);
        }
      }
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

fn pick_port() -> Result<u16, Box<dyn std::error::Error>> {
  let listener = TcpListener::bind("127.0.0.1:0")?;
  let port = listener.local_addr()?.port();
  drop(listener);
  Ok(port)
}

fn spawn_backend(app: &tauri::App<Wry>) -> Result<(String, Child), Box<dyn std::error::Error>> {
    let port = pick_port()?;
    let host = "127.0.0.1";
    let api_base = format!("http://{host}:{port}");

    if cfg!(debug_assertions) {
        let python =
            std::env::var("EASY_PYTHON_BIN").unwrap_or_else(|_| "python3".to_string());
        println!("[easy] using python backend: {}", python);
        let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..");
        let mut cmd = Command::new(python);
        cmd.args([
                "-m",
                "uvicorn",
                "api.server:app",
                "--host",
                host,
                "--port",
                &port.to_string(),
            ])
            .current_dir(repo_root)
            .stdin(Stdio::null());

        // On macOS/Unix, create a new process group so the Python process
        // doesn't inherit the terminal/dock association from the parent
        #[cfg(unix)]
        cmd.process_group(0);

        let child = cmd.spawn()?;
        wait_for_backend(host, port, Duration::from_secs(20))?;
        app.manage(api_base.clone());
        return Ok((api_base, child));
    } else {
        let backend_path = resolve_backend_path(app)?;
        let mut cmd = Command::new(backend_path);
        cmd.env("EASY_API_HOST", host)
            .env("EASY_API_PORT", port.to_string())
            .stdin(Stdio::null());

        #[cfg(unix)]
        cmd.process_group(0);

        let child = cmd.spawn()?;
        wait_for_backend(host, port, Duration::from_secs(20))?;
        app.manage(api_base.clone());
        return Ok((api_base, child));
    }
}

fn wait_for_backend(
    host: &str,
    port: u16,
    timeout: Duration,
) -> Result<(), Box<dyn std::error::Error>> {
    let addr: SocketAddr = format!("{host}:{port}").parse()?;
    let deadline = Instant::now() + timeout;
    loop {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(250)).is_ok() {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err("Backend did not start in time".into());
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

fn shutdown_backend(app: &tauri::AppHandle<Wry>) {
    if let Some(state) = app.try_state::<BackendChild>() {
        let child = state.0.lock().ok().and_then(|mut guard| guard.take());
        if let Some(mut child) = child {
            let _ = child.kill();
        }
    }
}

fn resolve_backend_path(app: &tauri::App<Wry>) -> Result<PathBuf, Box<dyn std::error::Error>> {
    if let Ok(path) = std::env::var("EASY_BACKEND_PATH") {
        return Ok(PathBuf::from(path));
    }

    let resources_dir = app
        .path()
        .resource_dir()
        .map_err(|err| format!("Unable to resolve app resources directory: {err}"))?;

    let target = env!("TAURI_ENV_TARGET_TRIPLE");
    let mut candidate = resources_dir.join("bin").join(format!("backend-{target}"));
    if cfg!(target_os = "windows") {
        candidate.set_extension("exe");
    }
    Ok(candidate)
}

fn build_about_metadata() -> AboutMetadata<'static> {
    let pkg_version = env!("CARGO_PKG_VERSION");
    let (commit_count, branch) = git_version_info();
    let version = match (commit_count, branch) {
        (Some(count), Some(branch)) => format!("{pkg_version} ({count} commits, {branch})"),
        _ => pkg_version.to_string(),
    };
    let summary = "Easy lets you control your computer with simple hand gestures, \
making everyday actions feel natural and effortless.";

    AboutMetadata {
        name: Some("Easy".to_string()),
        version: Some(version),
        short_version: Some(pkg_version.to_string()),
        copyright: Some("© 2025 Easy".to_string()),
        credits: Some(summary.to_string()),
        ..Default::default()
    }
}

fn git_version_info() -> (Option<String>, Option<String>) {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let commit_count = Command::new("git")
        .args(["rev-list", "--count", "HEAD"])
        .current_dir(&repo_root)
        .output()
        .ok()
        .and_then(|out| String::from_utf8(out.stdout).ok())
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());
    let branch = Command::new("git")
        .args(["rev-parse", "--abbrev-ref", "HEAD"])
        .current_dir(&repo_root)
        .output()
        .ok()
        .and_then(|out| String::from_utf8(out.stdout).ok())
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());
    (commit_count, branch)
}
