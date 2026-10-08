'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const actions = {am_in:'Morning In', am_out:'Morning Out', pm_in:'Afternoon In', pm_out:'Afternoon Out'};
let session, staff = [], office = {}, routeVersion = 0, toastTimer;
const ui = {attendanceDate:today(), attendanceMonth:today().slice(0,7), attendanceView:'day', employee:'', dutyDate:today(), reportMonth:today().slice(0,7), reportEmployee:''};

function today() { return new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Manila',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()); }
function displayDate(value, options = {}) { return new Intl.DateTimeFormat('en-PH', {timeZone:'Asia/Manila',day:'numeric',month:'short',year:'numeric',...options}).format(new Date(value.includes('T') ? value : value+'T12:00:00+08:00')); }
function displayTime(value) { return new Intl.DateTimeFormat('en-PH', {timeZone:'Asia/Manila',hour:'numeric',minute:'2-digit'}).format(new Date(value)); }
function initials(name) { return name.split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase(); }
function pill(text, kind='') { return `<span class="pill ${kind}">${esc(text)}</span>`; }
function empty(title, message) { return `<div class="empty"><strong>${esc(title)}</strong>${esc(message)}</div>`; }
function header(title, subtitle, extra='') { return `<div class="page-header"><div><p class="eyebrow">YOUR OFFICE, ORGANIZED</p><h1>${title}</h1><p class="muted">${subtitle}</p></div><div class="actions">${extra}</div></div>`; }
function person(emp) { return `<div class="person">${emp.has_photo ? `<img class="person-photo" src="/api/employees/${encodeURIComponent(emp.id)}/photo" alt="">` : `<span class="avatar">${esc(initials(emp.name))}</span>`}<div><strong>${esc(emp.name)}</strong><small>${esc(emp.employee_no)}</small></div></div>`; }
function employeeOptions(selected='', all=true) { return (all?'<option value="">All employees</option>':'<option value="">Select an employee</option>') + staff.map(emp=>`<option value="${esc(emp.id)}" ${selected===emp.id?'selected':''}>${esc(emp.name)}${emp.active?'':' (inactive)'}</option>`).join(''); }
function actionOptions(selected='am_in') { return Object.entries(actions).map(([key,label])=>`<option value="${key}" ${key===selected?'selected':''}>${label}</option>`).join(''); }

async function api(path, options={}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
    options.body = JSON.stringify(options.body);
  }
  if (session?.csrf) headers.set('X-CSRF-Token', session.csrf);
  let response;
  try { response = await fetch('/api'+path, {...options,headers}); }
  catch { setConnection(false); throw new Error('Server unavailable. Check the office network and try again.'); }
  setConnection(true);
  if (!response.ok) {
    const data = await response.json().catch(()=>({}));
    if (response.status===401 && path!=='/auth/login') showLogin();
    const detail = typeof data.detail==='string' ? data.detail : data.detail?.map(item=>`${item.loc.at(-1)}: ${item.msg}`).join('; ');
    throw new Error(detail || 'Request failed. Please try again.');
  }
  return response.json();
}
function setConnection(connected) {
  const label=$('#connection');
  label.textContent=connected?'Server connected':'Server unavailable';
  label.classList.toggle('offline',!connected);
}
function toast(message,error=false) {
  const el=$('#toast'); el.textContent=message; el.classList.toggle('error',error); el.hidden=false;
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.hidden=true,6000);
}
function showLogin() {
  session=null; $('#workspace').hidden=true; $('#login-screen').hidden=false;
  $('#modal').close(); $('#login-form').reset();
}
async function start(user) {
  session=user; $('#login-screen').hidden=true; $('#workspace').hidden=false;
  $('#user-name').textContent=user.name; $('#user-initial').textContent=initials(user.name);
  await refreshShared(); await render();
}
async function refreshShared() {
  [staff,office]=await Promise.all([api('/employees'),api('/settings')]);
}
function showModal(title, body, submit='Save') {
  $('#modal-content').innerHTML=`<div class="modal-header"><h2>${esc(title)}</h2><button class="icon-button" data-close aria-label="Close">×</button></div><form id="modal-form" class="modal-body">${body}<p class="form-error" role="alert"></p><div class="modal-footer"><button type="button" class="secondary" data-close>Cancel</button><button class="primary" type="submit">${esc(submit)}</button></div></form>`;
  $('#modal').showModal();
}
function bindModal(handler) {
  $('#modal-form').addEventListener('submit',async event=>{
    event.preventDefault(); const form=event.currentTarget,button=$('button[type=submit]',form); button.disabled=true;
    try { await handler(new FormData(form),form); $('#modal').close(); await refreshShared(); await render(); }
    catch(error) { $('.form-error',form).textContent=error.message; }
    finally { button.disabled=false; }
  });
}
function reasonModal(title, description, handler) {
  showModal(title,`<p class="muted">${esc(description)}</p><label>Reason<textarea name="reason" required minlength="5" maxlength="500"></textarea></label>`,'Confirm');
  bindModal(async data=>{await handler(data.get('reason')); toast('Change saved.');});
}

async function render() {
  if (!session) return;
  const route=(location.hash.slice(1)||'dashboard'); const version=++routeVersion;
  $$('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===route));
  $('#content').innerHTML='<div class="loading">Loading workspace…</div>';
  try {
    const views={dashboard,employees,attendance,field,reports,scanner,accounts,audit:auditView,settings:settingsView};
    const result=await (views[route]||dashboard)();
    if(version!==routeVersion || !session) return;
    $('#content').innerHTML=result; bindView(route);
  } catch(error) {
    if(version!==routeVersion || !session) return;
    $('#content').innerHTML=header('Unable to load this screen','Your existing records have not been changed.')+empty('Connection or request failed',error.message)+ '<button class="secondary" data-action="refresh">Try again</button>';
  }
}

function rowsTable(data, days, filterEmployee='', editing=false) {
  const relevant=staff.filter(e=>(!filterEmployee||filterEmployee===e.id) && (e.active||data.records.some(r=>r.employee_id===e.id)||data.field_duties.some(d=>d.employee_id===e.id)));
  const rows=[];
  for(const day of days) for(const emp of relevant) {
    const records=data.records.filter(r=>r.employee_id===emp.id && r.work_date===day && !r.voided);
    const duty=data.field_duties.find(d=>d.employee_id===emp.id && d.work_date===day);
    const slots=Object.keys(actions).map(action=>{
      const record=data.records.find(r=>r.employee_id===emp.id && r.work_date===day && r.action===action);
      const period=action.startsWith('am')?'morning':'afternoon';
      const covered=duty && (duty.period==='full_day'||duty.period===period);
      const content=record&&!record.voided?`${esc(displayTime(record.recorded_at))}${record.corrected?'<span class="corrected">Admin entry / corrected</span>':''}`:covered?pill('Field duty'):`<span class="missing">${record?.voided?'Voided entry':day>today()?'Pending':'No scan recorded'}</span>`;
      return `<td class="time-cell">${editing?`<button class="link-button" data-action="correct" data-employee="${emp.id}" data-date="${day}" data-slot="${action}" data-version="${record?.version||0}" data-id="${record?.id||''}" data-voided="${record?.voided||false}" data-time="${record&&!record.voided?esc(record.recorded_at.slice(11,16)):''}">${content}</button>`:content}</td>`;
    }).join('');
    rows.push(`<tr>${days.length>1?`<td>${esc(displayDate(day))}</td>`:''}<td>${person(emp)}</td>${slots}<td>${duty?pill(duty.period==='full_day'?'Field duty':'Partial field duty'):records.length===4?pill('4 entries'):pill(`${records.length}/4 entries`,'neutral')}</td></tr>`);
  }
  if(!rows.length) return empty('No employees to display','Add an employee to begin recording attendance.');
  return `<div class="table-wrap"><table><thead><tr>${days.length>1?'<th>Date</th>':''}<th>Employee</th>${Object.values(actions).map(label=>`<th>${label}</th>`).join('')}<th>Record</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

async function dashboard() {
  const day=today();
  const [data,devices,history]=await Promise.all([api(`/attendance?start=${day}&end=${day}`),api('/devices'),api('/audit?limit=5')]);
  const active=staff.filter(e=>e.active), arrived=new Set(data.records.filter(r=>!r.voided&&(r.action==='am_in'||r.action==='pm_in')).map(r=>r.employee_id)), duty=new Set(data.field_duties.map(d=>d.employee_id));
  const complete=active.filter(e=>data.records.filter(r=>r.employee_id===e.id&&!r.voided).length===4).length;
  const metric=(label,number,note,symbol)=>`<div class="metric"><div class="metric-label">${label}<span class="metric-symbol">${symbol}</span></div><div class="metric-number">${number}</div><small>${note}</small></div>`;
  return header('A clear view of your workday.','Today’s office attendance and approved field assignments.',`<span class="pill neutral">${esc(displayDate(day,{weekday:'short'}))}</span><a class="primary" href="#employees">＋ Add employee</a>`)+
    `<div class="metrics">${metric('Active employees',active.length,'Your registered team','♙')}${metric('Recorded arrivals',arrived.size,'At least one arrival scan today','↘')}${metric('On field duty',duty.size,'Full-day or half-day approvals','↗')}${metric('Complete records',complete,'All four attendance slots recorded','✓')}</div>`+
    `<section class="card"><div class="card-head"><div><h3>Today’s attendance</h3><p class="muted">Actual recorded times. Missing scans do not imply absence.</p></div><a href="#attendance" class="link-button">View records →</a></div>${rowsTable(data,[day])}</section>`+
    `<div class="two-column"><section class="card"><div class="card-head"><h3>Recent activity</h3><a href="#audit">View history →</a></div><div class="card-body">${history.length?history.map(h=>`<div class="feed-item"><span class="avatar">${esc(initials(h.actor))}</span><div><p>${esc(h.reason)}</p><small>${esc(h.actor)} · ${esc(displayDate(h.at))}, ${esc(displayTime(h.at))}</small></div></div>`).join(''):empty('No activity yet','Changes will appear here as your team starts using the system.')}</div></section><section class="card"><div class="card-head"><h3>Office essentials</h3>${devices.some(d=>d.active)?pill('Scanner enrolled'):pill('Setup needed','amber')}</div><div class="card-body"><div class="schedule-list">${Object.entries(actions).map(([key,label])=>`<div class="schedule-row"><span>${label}</span><strong>${esc(displayTime(`2000-01-01T${office[key]}:00+08:00`))}</strong></div>`).join('')}</div><p class="hint">Reference schedule only. No late or undertime calculations.</p><br><a class="secondary" href="#scanner">Manage scanner →</a></div></section></div>`;
}

async function employees() {
  await refreshShared();
  return header('Your team','Employee profiles and QR codes for printed IDs.', '<button class="primary" data-action="add-employee">＋ Add employee</button>')+
    `<div class="filters"><label class="search">Find an employee<input id="employee-search" type="search" placeholder="Search name or employee number"></label></div><section class="card">${staff.length?`<div class="table-wrap"><table><thead><tr><th>Employee</th><th>Position</th><th>Status</th><th>Manage</th></tr></thead><tbody id="employee-rows">${staff.map(emp=>`<tr data-search="${esc((emp.name+' '+emp.employee_no).toLowerCase())}"><td>${person(emp)}</td><td>${esc(emp.position)||'—'}</td><td>${pill(emp.active?'Active':'Inactive',emp.active?'':'neutral')}</td><td><div class="actions"><button class="link-button" data-action="edit-employee" data-id="${emp.id}">Edit</button><button class="link-button" data-action="photo" data-id="${emp.id}">Photo</button><a class="link-button" href="/api/employees/${emp.id}/id.pdf" target="_blank" rel="noopener">Print ID</a><button class="link-button" data-action="replace-qr" data-id="${emp.id}">Replace QR</button></div></td></tr>`).join('')}</tbody></table></div>`:empty('Your team starts here','Add your first employee, upload a photo, and print their QR ID.')}</section>`+
    '<div class="notice">QR codes contain random identifiers, not employee details. Replacing a QR code immediately disables the old printed ID.</div>';
}

function monthDays(month) {
  const [year,m]=month.split('-').map(Number), count=new Date(Date.UTC(year,m,0)).getUTCDate();
  return Array.from({length:count},(_,i)=>`${month}-${String(i+1).padStart(2,'0')}`);
}
async function attendance() {
  const days=ui.attendanceView==='day'?[ui.attendanceDate]:monthDays(ui.attendanceMonth);
  const data=await api(`/attendance?start=${days[0]}&end=${days.at(-1)}${ui.employee?'&employee_id='+ui.employee:''}`);
  return header('Attendance records','Review actual times and make accountable corrections.')+
    `<div class="filters"><label>View<select id="attendance-view"><option value="day" ${ui.attendanceView==='day'?'selected':''}>Daily</option><option value="month" ${ui.attendanceView==='month'?'selected':''}>Monthly</option></select></label><label>${ui.attendanceView==='day'?'Date':'Month'}<input id="attendance-period" type="${ui.attendanceView==='day'?'date':'month'}" value="${ui.attendanceView==='day'?ui.attendanceDate:ui.attendanceMonth}" required></label><label class="search">Employee<select id="attendance-employee">${employeeOptions(ui.employee)}</select></label><button class="secondary" data-action="refresh">Refresh</button></div>`+
    '<div class="notice">Select an attendance time or empty slot to correct it. Every change requires a reason and preserves its history. Field duty never creates scan times.</div>'+
    `<section class="card">${rowsTable(data,days,ui.employee,true)}</section>`;
}

async function field() {
  const data=await api(`/attendance?start=${ui.dutyDate}&end=${ui.dutyDate}`);
  return header('Field duty','Record existing office approvals without inventing attendance times.','<button class="primary" data-action="add-duty">＋ Record field duty</button>')+
    `<div class="filters"><label>Assignment date<input id="duty-date" type="date" value="${ui.dutyDate}" required></label></div><section class="card">${data.field_duties.length?`<div class="table-wrap"><table><thead><tr><th>Employee</th><th>Period</th><th>Location / purpose</th><th>Manage</th></tr></thead><tbody>${data.field_duties.map(d=>`<tr><td>${person(staff.find(e=>e.id===d.employee_id))}</td><td>${pill(d.period.replaceAll('_',' '))}</td><td class="history-details"><strong>${esc(d.location)}</strong><br><span>${esc(d.purpose)}</span></td><td><button class="link-button" data-action="edit-duty" data-id="${d.id}">Edit</button><button class="link-button" data-action="remove-duty" data-id="${d.id}" data-version="${d.version}">Remove</button></td></tr>`).join('')}</tbody></table></div>`:empty('No field assignments for this date','An admin can record full-day, morning, or afternoon official business.')}</section>`+
    '<div class="notice">Employees do not need to submit another app form. Follow your office’s existing approval process. Assignments also appear in a supplementary page with the monthly DTR.</div>';
}

async function reports() {
  const status=await api('/months/'+ui.reportMonth);
  const selected=staff.find(e=>e.id===ui.reportEmployee);
  const url=selected?`/api/reports/${selected.id}/${ui.reportMonth}.pdf`:'';
  return header('Monthly time records','Generate individual Civil Service Form 48 PDFs.',pill(status.finalized?'Month finalized':'Open for review',status.finalized?'':'amber'))+
    '<div class="notice amber">Verify the Form 48 layout and your office’s treatment of field duty before official use. Undertime fields stay blank; no automatic calculations are applied.</div>'+
    `<section class="card"><div class="card-body"><div class="report-controls"><label>Employee<select id="report-employee">${employeeOptions(ui.reportEmployee,false)}</select></label><label>Month<input id="report-month" type="month" value="${ui.reportMonth}" min="2000-01" max="2100-12" required></label>${url?`<a class="primary" href="${url}" target="_blank" rel="noopener">Open PDF / Print ↗</a>`:'<button class="primary" disabled>Select an employee</button>'}</div></div></section>`+
    `<section class="card"><div class="card-head"><h3>${selected?esc(selected.name)+' · '+esc(ui.reportMonth):'DTR preview'}</h3></div>${url?`<iframe title="Form 48 PDF preview" class="preview" src="${url}"></iframe>`:empty('Select an employee','Their monthly DTR will appear here, ready to download or print.')}</section>`+
    `<section class="card"><div class="card-body toolbar"><div><h3>Monthly review</h3><p class="muted">Finalization locks attendance and field-duty edits for the entire month.</p></div><button class="${status.finalized?'secondary':'primary'}" data-action="month-lock" data-mode="${status.finalized?'reopen':'finalize'}">${status.finalized?'Reopen month':'Finalize month'}</button></div></section>`;
}

async function scanner() {
  const devices=await api('/devices'), active=devices.find(d=>d.active);
  return header('One trusted scanner','Enroll the shared Android phone and revoke its access when needed.')+
    `<section class="card"><div class="card-head"><h3>Authorized phone</h3>${pill(active?'Enrolled':'Not enrolled',active?'':'amber')}</div><div class="card-body">${active?`<div class="device-card"><div class="device-icon">▣</div><div><h2>${esc(active.name)}</h2><p class="muted">Enrolled ${esc(displayDate(active.enrolled_at))}</p><p class="hint">Only this phone can submit signed QR attendance.</p></div><button class="danger" data-action="revoke-device" data-id="${active.id}">Revoke access</button></div>`:empty('Connect your scanning phone','Create a one-time code below, then enter it in the Android app while logged in as an operator.')}<br><button class="primary" data-action="enroll-code" ${active?'disabled':''}>Generate enrollment code</button><div id="enrollment-result"></div></div></section>`+
    '<div class="notice">Enrollment codes expire after 10 minutes and can be used once. A replacement phone can only be enrolled after revoking the current scanner.</div>'+
    `<section class="card"><div class="card-head"><h3>Device history</h3></div>${devices.length?`<div class="table-wrap"><table><thead><tr><th>Phone</th><th>Enrolled</th><th>Status</th></tr></thead><tbody>${devices.map(d=>`<tr><td>${esc(d.name)}</td><td>${esc(displayDate(d.enrolled_at))}</td><td>${pill(d.active?'Authorized':'Revoked',d.active?'':'neutral')}</td></tr>`).join('')}</tbody></table></div>`:empty('No devices yet','Enroll the designated phone to enable QR attendance.')}</section>`;
}

async function accounts() {
  const values=await api('/accounts');
  return header('Admin & operator accounts','Individual logins keep actions accountable.','<button class="primary" data-action="add-account">＋ Create account</button>')+
    `<section class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th>Manage</th></tr></thead><tbody>${values.map(u=>`<tr><td>${esc(u.name)}</td><td>${esc(u.username)}</td><td>${pill(u.role)}</td><td>${pill(u.active?'Active':'Disabled',u.active?'':'neutral')}</td><td><button class="link-button" data-action="reset-password" data-id="${u.id}" data-active="${u.active}">Reset password</button>${u.id!==session.id?`<button class="link-button" data-action="toggle-account" data-id="${u.id}" data-active="${u.active}">${u.active?'Disable':'Enable'}</button>`:''}</td></tr>`).join('')}</tbody></table></div></section>`+
    '<div class="notice">Operators can enroll the phone with an admin-issued code and scan attendance. They cannot edit records, manage employees, or access the admin dashboard.</div>';
}

async function auditView() {
  const values=await api('/audit?limit=200');
  return header('Change history','Original records, reasons, and the people behind each action.')+
    `<section class="card">${values.length?`<div class="table-wrap"><table><thead><tr><th>When</th><th>Who</th><th>Action / reason</th><th>Details</th></tr></thead><tbody>${values.map(a=>`<tr><td>${esc(displayDate(a.at))}<br><small>${esc(displayTime(a.at))}</small></td><td>${esc(a.actor)}</td><td class="history-details"><strong>${esc(a.kind.replaceAll('.',' · ').replaceAll('_',' '))}</strong><br>${esc(a.reason)}</td><td><details><summary>Before / after</summary><pre class="history-json">${esc(JSON.stringify({before:a.before,after:a.after},null,2))}</pre></details></td></tr>`).join('')}</tbody></table></div>`:empty('No changes yet','Attendance scans and administrative actions will be recorded here.')}</section><p class="hint">Showing the latest 200 actions. Audit history cannot be edited from the app.</p>`;
}

async function settingsView() {
  return header('Office settings','Schedule references and report signature details.')+
    `<section class="card"><div class="card-body"><form id="settings-form" class="form-grid"><label class="full-width">Office name<input name="office_name" value="${esc(office.office_name)}" required maxlength="120"></label><label>Report signatory<input name="signatory" value="${esc(office.signatory)}" maxlength="120"></label><label>Signatory title<input name="signatory_title" value="${esc(office.signatory_title)}" maxlength="120"></label>${Object.entries(actions).map(([key,label])=>`<label>${label}<input name="${key}" type="time" value="${office[key]}" required></label>`).join('')}<div class="notice full-width">Timezone: Asia/Manila. These hours are references only. Late, grace-period, and undertime rules are not applied.</div><p class="form-error full-width" role="alert"></p><div class="full-width"><button class="primary" type="submit">Save settings</button></div></form></div></section>`;
}

function bindView(route) {
  if(route==='employees') $('#employee-search')?.addEventListener('input',event=>{
    $$('#employee-rows tr').forEach(row=>row.hidden=!row.dataset.search.includes(event.target.value.toLowerCase()));
  });
  for(const [id,key] of [['attendance-view','attendanceView'],['attendance-employee','employee'],['duty-date','dutyDate'],['report-month','reportMonth'],['report-employee','reportEmployee']]) {
    $('#'+id)?.addEventListener('change',event=>{if(!event.target.value && event.target.required) return; ui[key]=event.target.value; render();});
  }
  $('#attendance-period')?.addEventListener('change',event=>{if(!event.target.value)return; ui[ui.attendanceView==='day'?'attendanceDate':'attendanceMonth']=event.target.value;render();});
  $('#settings-form')?.addEventListener('submit',async event=>{
    event.preventDefault(); const form=event.currentTarget,button=$('button',form);button.disabled=true;
    try {await api('/settings',{method:'PUT',body:Object.fromEntries(new FormData(form))});await refreshShared();toast('Office settings saved.');}
    catch(error){$('.form-error',form).textContent=error.message;}finally{button.disabled=false;}
  });
}

function employeeModal(id) {
  const emp=id?staff.find(e=>e.id===id):{name:'',employee_no:'',position:'',active:true};
  showModal(id?'Edit employee':'Add employee',`<label>Employee number<input name="employee_no" value="${esc(emp.employee_no)}" required maxlength="40"></label><label>Full name<input name="name" value="${esc(emp.name)}" required maxlength="120"></label><label>Position<input name="position" value="${esc(emp.position)}" maxlength="120"></label><label class="checkbox-label"><input name="active" type="checkbox" ${emp.active?'checked':''}> Active employee</label>`);
  bindModal(async data=>{await api('/employees'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{employee_no:data.get('employee_no'),name:data.get('name'),position:data.get('position'),active:data.has('active')}});toast('Employee saved.');});
}

function correctionModal(button) {
  const emp=staff.find(e=>e.id===button.dataset.employee);
  showModal('Review attendance',`<p class="muted">${esc(emp.name)} · ${esc(displayDate(button.dataset.date))}</p><label>Attendance action<input value="${actions[button.dataset.slot]}" disabled></label><label>Actual time (Philippine time)<input name="local_time" type="time" value="${button.dataset.time}" required></label><label>Reason for entry or correction<textarea name="reason" required minlength="5" maxlength="500" placeholder="Explain the source of the actual time"></textarea></label><p class="hint">The original time is retained. Do not use a field-duty approval to invent an arrival or departure time.</p>`);
  bindModal(async data=>{await api('/attendance/correct',{method:'POST',body:{employee_id:emp.id,work_date:button.dataset.date,action:button.dataset.slot,local_time:data.get('local_time'),reason:data.get('reason'),expected_version:Number(button.dataset.version)}});toast('Attendance saved with its correction history.');});
  if(button.dataset.id&&button.dataset.voided==='false') {
    const remove=document.createElement('button');remove.type='button';remove.className='danger';remove.textContent='Void mistaken entry';
    remove.addEventListener('click',()=>{
      $('#modal').close();
      reasonModal('Void mistaken attendance','This removes the time from the DTR while retaining the original record and audit history.',reason=>api(`/attendance/${button.dataset.id}/void`,{method:'POST',body:{reason,expected_version:Number(button.dataset.version)}}));
    });
    $('.modal-footer').prepend(remove);
  }
}

async function dutyModal(id) {
  const data=await api(`/attendance?start=${ui.dutyDate}&end=${ui.dutyDate}`),duty=id?data.field_duties.find(d=>d.id===id):null;
  showModal(duty?'Edit field duty':'Record field duty',`<label>Employee<select name="employee_id" required ${duty?'disabled':''}>${employeeOptions(duty?.employee_id||'',false)}</select></label><label>Date<input name="work_date" type="date" value="${duty?.work_date||ui.dutyDate}" required ${duty?'disabled':''}></label><label>Period<select name="period">${[['full_day','Full day'],['morning','Morning'],['afternoon','Afternoon']].map(([k,label])=>`<option value="${k}" ${duty?.period===k?'selected':''}>${label}</option>`).join('')}</select></label><label>Location<input name="location" value="${esc(duty?.location||'')}" required maxlength="200"></label><label>Purpose<input name="purpose" value="${esc(duty?.purpose||'')}" required maxlength="500"></label><label>Approval note / reason<textarea name="reason" required minlength="5" maxlength="500"></textarea></label>`);
  bindModal(async values=>{
    const body=Object.fromEntries(values);body.employee_id=duty?.employee_id||body.employee_id;body.work_date=duty?.work_date||body.work_date;
    body.expected_version=duty?.version||0;
    await api('/field-duty',{method:'POST',body});ui.dutyDate=body.work_date;toast('Field-duty approval recorded. Attendance times were not changed.');
  });
}

document.addEventListener('click',async event=>{
  const close=event.target.closest('[data-close]');if(close){event.preventDefault();$('#modal').close();return;}
  const button=event.target.closest('[data-action]');if(!button)return;
  const action=button.dataset.action;
  try {
    if(action==='refresh'){await refreshShared();await render();}
    if(action==='add-employee')employeeModal();
    if(action==='edit-employee')employeeModal(button.dataset.id);
    if(action==='correct')correctionModal(button);
    if(action==='add-duty')await dutyModal();
    if(action==='edit-duty')await dutyModal(button.dataset.id);
    if(action==='remove-duty')reasonModal('Remove field duty','This removes the approval while retaining its audit history.',reason=>api(`/field-duty/${button.dataset.id}?version=${button.dataset.version}`,{method:'DELETE',body:{reason}}));
    if(action==='replace-qr')reasonModal('Replace printed ID QR','The current QR code will stop working immediately. Print a new ID after replacement.',reason=>api(`/employees/${button.dataset.id}/replace-qr`,{method:'POST',body:{reason}}));
    if(action==='revoke-device')reasonModal('Revoke scanner access','This phone will no longer be able to record attendance.',reason=>api(`/devices/${button.dataset.id}/revoke`,{method:'POST',body:{reason}}));
    if(action==='photo'){
      showModal('Employee photo','<label>Photo<input type="file" name="file" accept="image/jpeg,image/png,image/webp" required></label><p class="hint">JPEG, PNG, or WebP. Maximum 2 MB and 16 megapixels.</p>','Upload photo');
      bindModal(async data=>{await api(`/employees/${button.dataset.id}/photo`,{method:'POST',body:data});toast('Photo updated.');});
    }
    if(action==='enroll-code'){
      button.disabled=true;const data=await api('/devices/enrollment-code',{method:'POST'});
      $('#enrollment-result').innerHTML=`<p class="hint">Enter this code on the operator’s phone. Expires at ${esc(displayTime(data.expires_at))}.</p><div class="code-box">${esc(data.code)}</div><p class="hint">Generating another code invalidates this one.</p>`;
      button.disabled=false;
    }
    if(action==='month-lock'){
      const mode=button.dataset.mode;
      showModal(mode==='finalize'?'Finalize monthly records':'Reopen monthly records',`<p class="muted">${mode==='finalize'?'Review incomplete entries and field assignments first. This locks all employees’ records for':'Reopening permits audited edits for'} ${esc(ui.reportMonth)}.</p>${mode==='finalize'?'<label class="checkbox-label"><input name="reviewed" type="checkbox" required> I reviewed missing entries and field-duty records.</label>':''}<label>Reason<textarea name="reason" required minlength="5" maxlength="500"></textarea></label>`,mode==='finalize'?'Finalize':'Reopen');
      bindModal(async data=>{await api(`/months/${ui.reportMonth}/${mode}`,{method:'POST',body:{reason:data.get('reason')}});toast('Monthly status updated.');});
    }
    if(action==='add-account'){
      showModal('Create account','<label>Full name<input name="name" required maxlength="120"></label><label>Username<input name="username" required pattern="[a-zA-Z0-9_.-]{3,80}" autocomplete="off"></label><label>Role<select name="role"><option value="operator">Operator — scanner only</option><option value="admin">Administrator — dashboard</option></select></label><label>Password<input name="password" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label>');
      bindModal(async data=>{await api('/accounts',{method:'POST',body:Object.fromEntries(data)});toast('Account created.');});
    }
    if(action==='toggle-account')reasonModal(button.dataset.active==='true'?'Disable account':'Enable account','Changing access invalidates existing sessions.',reason=>api('/accounts/'+button.dataset.id,{method:'PUT',body:{active:button.dataset.active!=='true',reason}}));
    if(action==='reset-password'){
      showModal('Reset password','<label>New password<input name="password" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label><p class="hint">Existing sessions will be invalidated.</p>');
      bindModal(async data=>{await api('/accounts/'+button.dataset.id,{method:'PUT',body:{active:button.dataset.active==='true',password:data.get('password')}});toast('Password reset.');});
    }
  } catch(error) {button.disabled=false;toast(error.message,true);}
});

$('#login-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=$('button',form);button.disabled=true;$('#login-error').textContent='';
  try {const user=await api('/auth/login',{method:'POST',body:{...Object.fromEntries(new FormData(form)),client:'web'}});form.reset();await start(user);}
  catch(error){$('#login-error').textContent=error.message;}finally{button.disabled=false;}
});
$('#logout').addEventListener('click',async()=>{try{await api('/auth/logout',{method:'POST'});showLogin();}catch(error){toast(error.message,true);}});
window.addEventListener('hashchange',render);
setInterval(()=>{
  $('#clock-label').textContent=displayDate(today(),{weekday:'short'});
  if(!session)return;
  api('/health').catch(()=>{});
  if((!location.hash||location.hash==='#dashboard')&&!$('#modal').open)render();
},15000);
(async()=>{
  $('#clock-label').textContent=displayDate(today(),{weekday:'short'});
  try {const user=await api('/auth/me');if(user.role==='admin')await start(user);else showLogin();}
  catch {showLogin();}
})();
