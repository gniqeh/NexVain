"""Static, client-only demonstration form on published Dcell outer pages.

No network requests, database writes, or modifications to Dcell ZIP content.
"""
from __future__ import annotations

import html


STYLE = """
<style id="nva-demo-application-style">
.stage{position:relative}
.stage-inner>h1{padding-right:210px}
.nva-apply-open{position:absolute;top:37px;right:48px;z-index:5;padding:12px 22px;border:1px solid rgba(255,255,255,.2);border-radius:9px;background:var(--accent);color:#061422;font:700 17px 'Microsoft YaHei',sans-serif;cursor:pointer;box-shadow:0 5px 18px #0003}
.nva-apply-open:hover{filter:brightness(1.12)}
.nva-apply-open:focus-visible,.nva-apply-modal button:focus-visible,.nva-apply-modal input:focus-visible,.nva-apply-modal textarea:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.nva-apply-backdrop{position:absolute;inset:0;z-index:2000;background:rgba(2,12,25,.76);display:flex;align-items:center;justify-content:center;padding:30px}
.nva-apply-backdrop[hidden]{display:none}
.nva-apply-modal{width:680px;max-height:980px;overflow-y:auto;background:#f9fbfd;color:#203247;border-radius:16px;padding:34px 40px;box-shadow:0 20px 70px #0008;font:16px 'Microsoft YaHei',sans-serif}
.nva-apply-modal *{box-sizing:border-box}
.nva-apply-head{display:flex;justify-content:space-between;align-items:center;gap:20px}
.nva-apply-head h2{font-size:27px;margin:0}
.nva-apply-close{background:transparent;border:0;color:#627487;font-size:32px;cursor:pointer}
.nva-apply-subtitle{margin:7px 0 22px;color:#64748b;font-size:14px}
.nva-apply-resource{border:1px solid #d9e6ed;background:#edf6f9;border-radius:9px;padding:15px 18px;margin-bottom:20px;overflow-wrap:anywhere}
.nva-apply-resource small{display:block;color:#607b88;margin-bottom:7px}
.nva-apply-resource strong{font-size:17px}
.nva-apply-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.nva-apply-field{display:block;margin:0 0 16px;font-weight:600;font-size:15px}
.nva-apply-field input,.nva-apply-field textarea{display:block;width:100%;margin-top:8px;border:1px solid #b9c9d5;border-radius:8px;background:#fff;color:#203247;padding:11px 13px;font:15px 'Microsoft YaHei',sans-serif;resize:vertical}
.nva-apply-field textarea{min-height:82px}
.nva-apply-note{font-size:13px;color:#66778b;line-height:1.7;margin:1px 0 18px}
.nva-apply-actions{display:flex;justify-content:flex-end;gap:12px}
.nva-apply-actions button,.nva-apply-done{cursor:pointer;border-radius:8px;padding:12px 23px;border:1px solid #b3c7d4;background:white;color:#203247;font-weight:600;font-size:15px}
.nva-apply-actions button[type=submit],.nva-apply-done{background:#087f92;color:#fff;border-color:#087f92}
.nva-apply-success{text-align:center;padding:24px 0 6px}
.nva-apply-success h3{font-size:24px;margin:10px 0}
.nva-apply-success p{line-height:1.8;color:#53687c}
</style>
"""

MODAL = """
<div id="nva-apply-backdrop" class="nva-apply-backdrop" hidden>
  <section class="nva-apply-modal" role="dialog" aria-modal="true" aria-labelledby="nva-apply-title">
    <div class="nva-apply-head"><h2 id="nva-apply-title">数据使用申请</h2><button type="button" class="nva-apply-close" id="nva-apply-close" aria-label="关闭申请窗口">&times;</button></div>
    <p class="nva-apply-subtitle">NexVain · 数据资源申请演示</p>
    <div class="nva-apply-resource"><small>当前申请的数据集 · ID __ID__</small><strong>__NAME__</strong></div>
    <form id="nva-apply-form">
      <div class="nva-apply-row">
        <label class="nva-apply-field">申请人 *<input name="applicant" required maxlength="80" autocomplete="name" placeholder="请输入姓名"></label>
        <label class="nva-apply-field">所属机构 *<input name="organization" required maxlength="160" placeholder="请输入单位名称"></label>
      </div>
      <label class="nva-apply-field">联络邮箱 *<input type="email" name="email" required maxlength="180" placeholder="example@institution.cn"></label>
      <label class="nva-apply-field">申请说明 *<textarea name="purpose" required maxlength="1500" placeholder="请说明拟申请数据的用途"></textarea></label>
      <label class="nva-apply-field">备注（选填）<textarea name="remarks" maxlength="1500" placeholder="其他需要说明的信息"></textarea></label>
      <p class="nva-apply-note">演示说明：当前仅模拟申请流程，填写的信息不会被发送或保存，也不构成数据授权。</p>
      <div class="nva-apply-actions"><button type="button" id="nva-apply-cancel">取消</button><button type="submit">提交申请</button></div>
    </form>
    <div id="nva-apply-success" class="nva-apply-success" hidden>
      <h3>模拟提交完成</h3>
      <p>您已完成申请流程演示。当前页面不会实际提交、保存或发送申请信息。</p>
      <button type="button" class="nva-apply-done" id="nva-apply-done">完成</button>
    </div>
  </section>
</div>
"""

SCRIPT = """
<script id="nva-demo-application-script">
(function(){
  'use strict';
  var trigger=document.getElementById('nva-apply-open');
  var backdrop=document.getElementById('nva-apply-backdrop');
  var close=document.getElementById('nva-apply-close');
  var cancel=document.getElementById('nva-apply-cancel');
  var done=document.getElementById('nva-apply-done');
  var form=document.getElementById('nva-apply-form');
  var success=document.getElementById('nva-apply-success');
  if(!trigger || !backdrop || !form)return;
  function hide(){
    backdrop.hidden=true;
    form.reset();
    form.hidden=false;
    success.hidden=true;
    trigger.focus();
  }
  function show(){
    form.reset();
    form.hidden=false;
    success.hidden=true;
    backdrop.hidden=false;
    document.getElementById('nva-apply-title').focus();
    form.elements.applicant.focus();
  }
  trigger.addEventListener('click',show);
  close.addEventListener('click',hide);
  cancel.addEventListener('click',hide);
  done.addEventListener('click',hide);
  backdrop.addEventListener('click',function(event){if(event.target===backdrop)hide();});
  document.addEventListener('keydown',function(event){
    if(backdrop.hidden)return;
    if(event.key==='Escape'){event.preventDefault();hide();}
    if(event.key==='Tab'){
      var candidates=Array.from(backdrop.querySelectorAll('button,input,textarea')).filter(function(el){return el.getClientRects().length>0 && !el.disabled;});
      if(!candidates.length)return;
      var first=candidates[0],last=candidates[candidates.length-1];
      if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
    }
  });
  form.addEventListener('submit',function(event){
    event.preventDefault();
    if(!form.reportValidity())return;
    form.reset();
    form.hidden=true;
    success.hidden=false;
    done.focus();
  });
})();
</script>
"""


def decorate_dcell_page(page: str, dcell_id: int, dcell_name: str) -> str:
    """Add a self-contained demonstration button/dialog to the outer Dcell shell."""
    marker = '<main class="stage">'
    shell_end = '</main></div>\n    <script>'
    if marker not in page or shell_end not in page:
        raise ValueError("NexVain Dcell shell structure changed; application overlay not injected")
    button = '<button type="button" id="nva-apply-open" class="nva-apply-open" aria-haspopup="dialog">申请数据</button>'
    modal = MODAL.replace('__ID__', str(int(dcell_id))).replace('__NAME__', html.escape(dcell_name, quote=True))
    page = page.replace('</style>', STYLE + '</style>', 1)
    page = page.replace(marker, marker + button, 1)
    page = page.replace(shell_end, '</main>' + modal + '</div>\n    <script>', 1)
    return page.replace('</body>', SCRIPT + '</body>', 1)
