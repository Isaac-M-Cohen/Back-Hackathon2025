use std::net::TcpListener;

use tauri::{Manager, Wry};

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
      app.emit_all("easy://api-base", api_base.clone())?;

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

  let mut cmd = if cfg!(debug_assertions) {
    let python = std::env::var("EASY_PYTHON_BIN").unwrap_or_else(|_| "python3".to_string());
    let mut cmd = tauri::process::Command::new(python);
    cmd.args([
      "-m",
      "uvicorn",
      "api.server:app",
      "--host",
      host,
      "--port",
      &port.to_string(),
    ]);
    cmd
  } else {
    let mut cmd = tauri::process::Command::new_sidecar("backend")?;
    cmd.env("EASY_API_HOST", host);
    cmd.env("EASY_API_PORT", port.to_string());
    cmd
  };

  let (mut rx, _child) = cmd.spawn()?;
  tauri::async_runtime::spawn(async move {
    while let Some(event) = rx.recv().await {
      if let tauri::process::CommandEvent::Stderr(line) = event {
        log::warn!("backend: {}", line);
      }
    }
  });

  app.manage(api_base.clone());
  Ok(api_base)
}
