import os
import sys

# Ensure root directory is in sys.path so modules (app, config, utils, etc.) can be found
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from app import create_app
    app = create_app()
except Exception as exc:
    import traceback
    from flask import Flask, render_template_string

    err_str = str(exc)
    tb_str = traceback.format_exc()
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catch_all(path):
        return (
            render_template_string(
                """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Configuration Required – NewsSphere</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      padding: 1.5rem;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 80vh;
      margin: 0;
    }
    .card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 14px;
      padding: 2.2rem;
      max-width: 680px;
      width: 100%;
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    }
    h1 {
      color: #fb7185;
      margin-top: 0;
      font-size: 1.4rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    p { line-height: 1.6; color: #94a3b8; font-size: 0.95rem; }
    code {
      background: #090d16;
      color: #38bdf8;
      padding: 0.2rem 0.45rem;
      border-radius: 4px;
      font-size: 0.88em;
    }
    pre {
      background: #090d16;
      color: #fca5a5;
      padding: 1rem;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 0.85rem;
      border: 1px solid #334155;
      white-space: pre-wrap;
    }
    ol { color: #cbd5e1; padding-left: 1.2rem; font-size: 0.95rem; }
    li { margin-bottom: 0.75rem; line-height: 1.5; }
    .badge {
      display: inline-block;
      background: #3b82f6;
      color: white;
      padding: 0.15rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>⚠️ Application Startup Notice</h1>
    <p>The app started on Vercel, but encountered an initialization issue:</p>
    <pre>{{ err_str }}</pre>
    <h3 style="color: #e2e8f0; margin-top: 1.5rem;">Steps to complete setup:</h3>
    <ol>
      <li>
        <strong>Add Environment Variables in Vercel:</strong><br>
        Go to your Vercel Dashboard &rarr; <strong>Settings</strong> &rarr; <strong>Environment Variables</strong> and add:
        <br><code>MONGODB_URI</code>, <code>SECRET_KEY</code>, <code>JWT_SECRET</code>, and <code>SEED_ON_EMPTY=true</code>.
      </li>
      <li>
        <strong>Whitelist IP in MongoDB Atlas:</strong><br>
        Go to MongoDB Atlas &rarr; <strong>Network Access</strong> &rarr; Add <code>0.0.0.0/0</code> (Allow Access from Anywhere).
      </li>
      <li>
        <strong>Redeploy:</strong><br>
        In Vercel Deployments, click <strong>Redeploy</strong> to apply the changes.
      </li>
    </ol>
  </div>
</body>
</html>""",
                err_str=err_str,
            ),
            500,
        )

handler = app

