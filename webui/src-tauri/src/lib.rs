use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::Command;
use std::time::{Duration, Instant};

use tauri::{Emitter, Listener, Manager, Wry};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      let api_base = spawn_backend(app)?;
      app.emit("easy://api-base", api_base.clone())?;

      let app_handle = app.handle().clone();
      let app_handle_for_event = app_handle.clone();
      app_handle.listen("easy://frontend-ready", move |_| {
        if let Some(window) = app_handle_for_event.get_webview_window("main") {
          let _ = window.show();
          let _ = window.set_focus();
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
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

fn pick_port() -> Result<u16, Box<dyn std::error::Error>> {
  let listener = TcpListener::bind("127.0.0.1:0")?;
  let port = listener.local_addr()?.port();
  drop(listener);
  Ok(port)
}

fn spawn_backend(app: &tauri::App<Wry>) -> Result<String, Box<dyn std::error::Error>> {
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
        Command::new(python)
            .args([
                "-m",
                "uvicorn",
                "api.server:app",
                "--host",
                host,
                "--port",
                &port.to_string(),
            ])
            .current_dir(repo_root)
            .spawn()?;
    } else {
        let backend_path = resolve_backend_path()?;
        Command::new(backend_path)
            .env("EASY_API_HOST", host)
            .env("EASY_API_PORT", port.to_string())
            .spawn()?;
    }

    wait_for_backend(host, port, Duration::from_secs(10))?;
    app.manage(api_base.clone());
    Ok(api_base)
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

fn resolve_backend_path() -> Result<PathBuf, Box<dyn std::error::Error>> {
    if let Ok(path) = std::env::var("EASY_BACKEND_PATH") {
        return Ok(PathBuf::from(path));
    }

    let exe = std::env::current_exe()?;
    let resources_dir = exe
        .parent()
        .and_then(|p| p.parent())
        .map(|p| p.join("Resources"))
        .ok_or("Unable to resolve app Resources directory")?;

    let target = env!("TAURI_ENV_TARGET_TRIPLE");
    let candidate = resources_dir.join("bin").join(format!("backend-{target}"));
    Ok(candidate)
}
