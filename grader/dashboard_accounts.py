"""Account pages using the dashboard's typography, colors, cards and theme."""
import html
import json

from . import dashboard


def render(token, *, mode="login", error=""):
    creating = mode != "login"
    title = {"login": "Professor sign in", "setup": "Create professor account",
             "invite": "Invite professor"}[mode]
    description = {"login": "Sign in to your private grading workspace.",
                   "setup": "Create the first professor login to start reviewing projects.",
                   "invite": "Create a login for another professor. Their workspace will be separate from yours."}[mode]
    action = "/setup" if mode == "setup" else "/login"
    button = "Create professor login" if mode == "invite" else "Create account" if creating else "Sign in"
    # Reuse the actual dashboard stylesheet so both surfaces stay in sync.
    styles = dashboard.TEMPLATE.partition("<style>")[2].partition("</style>")[0]
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">'''
    page += "<title>" + title + " · Grading Dashboard</title>"
    page += '''<script>try {const theme=localStorage.getItem("dash-theme");
if(theme) document.documentElement.setAttribute("data-theme",theme);} catch(e) {}</script>'''
    page += '<style>' + styles + '''
.account-wrap{max-width:480px;padding-top:clamp(32px,10vh,100px)}
.account-brand{margin-bottom:24px}.account-card{padding:28px}
.account-card h1{margin-bottom:8px}.account-card p{margin:0 0 24px}
.account-card label{display:grid;gap:6px;margin:18px 0;font-weight:500}
.account-card input{width:100%;min-width:0;padding:10px 12px;border:1px solid var(--border);
 border-radius:8px;background:var(--surface);color:var(--text);font:inherit}
.account-card input:focus-visible,.account-card button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.account-card .submit{width:100%;padding:10px 12px;background:var(--accent);color:var(--surface);border-color:var(--accent)}
.account-card .submit:disabled{opacity:.6}.account-card .account-message:empty{display:none}
.account-card .account-message{margin:16px 0}.account-back{display:inline-block;margin-bottom:18px}
@media(max-width:480px){.account-card{padding:20px}}
</style></head><body><main class="wrap account-wrap">
<header class="top account-brand"><strong>Grading Dashboard</strong><button class="btn" id="theme" type="button">Theme</button></header>'''
    if mode == "invite":
        page += '<a class="account-back" href="/">← Back to dashboard</a>'
    page += '<section class="card account-card"><h1>' + title + '</h1><p class="muted">' + description + '</p>'
    page += '<form id="account-form" method="post" action="' + action + '"><input type="hidden" name="csrf" value="' + html.escape(token, quote=True) + '">'
    page += '<label>Username<input name="username" autocomplete="' + ('off' if creating else 'username') + '" maxlength="64" required autofocus></label>'
    page += '<label>Password<input name="password" type="password" autocomplete="' + ('new-password' if creating else 'current-password') + '" maxlength="1024"' + (' minlength="12"' if creating else '') + ' required></label>'
    if creating:
        page += '<p class="small muted">Use at least 12 characters.</p><label>Confirm password<input name="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required></label>'
    page += '<p id="account-message" class="account-message warn" role="alert">' + html.escape(error) + '</p><button class="btn submit" type="submit">' + button + '</button></form></section></main>'
    page += '''<script>
document.getElementById("theme").onclick=()=>{const root=document.documentElement;
const dark=root.getAttribute("data-theme")==="dark" || (!root.hasAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
const next=dark?"light":"dark";root.setAttribute("data-theme",next);
try{localStorage.setItem("dash-theme",next);}catch(e){}};
</script>'''
    if mode == "invite":
        page += '<script>const csrf=' + json.dumps(token).replace('<', '\\u003c') + ';'
        page += '''document.getElementById("account-form").onsubmit=async event=>{
event.preventDefault();const form=event.currentTarget,button=form.querySelector("button"),message=document.getElementById("account-message");
button.disabled=true;message.textContent="";
try{const fields=Object.fromEntries(new FormData(form));delete fields.csrf;
const response=await fetch("/api/professors",{method:"POST",headers:{"Content-Type":"application/json","X-Dashboard-Token":csrf},body:JSON.stringify(fields)});
if(response.status===401){location.assign("/login");return;}
const result=await response.json();if(!response.ok)throw new Error(result.error||"Account creation failed");
form.reset();message.textContent="Professor login created. They can now sign in to their own workspace.";
}catch(error){message.textContent=error.message;}finally{button.disabled=false;}};</script>'''
    return page + '</body></html>'
