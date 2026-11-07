
(function(){
var d=document,$=function(s){return d.querySelector(s)};
$('#theme').onclick=function(){
 var t=d.documentElement.dataset.theme==='dark'?'light':'dark';
 d.documentElement.dataset.theme=t;
 this.textContent=t==='dark'?'☀':'☾';
 this.setAttribute('aria-label',t==='dark'?'Ativar tema claro':'Ativar tema escuro');
 try{localStorage.setItem('ls-theme',t)}catch(e){}
};
var menu=$('#menu'),side=$('.side');
function setMenu(open){
 if(!menu||!side)return;
 side.classList.toggle('open',open);
 menu.setAttribute('aria-expanded',open?'true':'false');
 document.body.classList.toggle('nav-open',open);
}
menu.onclick=function(){setMenu(!side.classList.contains('open'))};
side.addEventListener('click',function(e){if(e.target.closest('a'))setMenu(false)});

d.querySelectorAll('.copy').forEach(function(b){b.onclick=function(){var t=b.parentNode.querySelector('code').innerText;(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).catch(function(){var a=d.createElement('textarea');a.value=t;d.body.appendChild(a);a.select();d.execCommand('copy');a.remove()});b.textContent='Copiado!';setTimeout(function(){b.textContent='Copiar'},1200)}});
var act=$('.side a.on');if(act)act.scrollIntoView({block:'center'});
var tl=[].slice.call(d.querySelectorAll('.toc a'));if(tl.length&&'IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){tl.forEach(function(a){a.classList.toggle('on',a.getAttribute('href')==='#'+e.target.id)})}})},{rootMargin:'-70px 0px -70% 0px'});tl.forEach(function(a){var t=d.getElementById(a.getAttribute('href').slice(1));if(t)io.observe(t)})}
var box=$('#sbox'),q=$('#q'),res=$('#res'),sel=0;
function open(){box.hidden=false;q.value='';render('');q.focus()}function close(){box.hidden=true}
$('#searchbtn').onclick=open;box.onclick=function(e){if(e.target===box)close()};
d.addEventListener('keydown',function(e){var typing=/INPUT|TEXTAREA/.test((d.activeElement||{}).tagName||'');if((e.key==='/'&&!typing)||((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k')){e.preventDefault();open()}else if(e.key==='Escape'){close();setMenu(false)}else if(!box.hidden&&(e.key==='ArrowDown'||e.key==='ArrowUp')){e.preventDefault();var l=res.querySelectorAll('a');if(!l.length)return;sel=(sel+(e.key==='ArrowDown'?1:-1)+l.length)%l.length;l.forEach(function(a,i){a.classList.toggle('sel',i===sel)});l[sel].scrollIntoView({block:'nearest'})}else if(!box.hidden&&e.key==='Enter'){var s=res.querySelector('a.sel')||res.querySelector('a');if(s)location.href=s.href}});
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function render(v){v=v.trim().toLowerCase();var out=[];var D=window.DOCS||[];if(v){var terms=v.split(/\s+/);D.forEach(function(x){var t=x.t.toLowerCase(),de=(x.d||'').toLowerCase(),sc=0;terms.forEach(function(w){if(t===w)sc+=50;else if(t.indexOf(w)===0)sc+=30;else if(t.indexOf(w)>-1)sc+=18;else if(de.indexOf(w)>-1)sc+=4;else sc=-999});if(sc>0)out.push([sc,x])});out.sort(function(a,b){return b[0]-a[0]});out=out.slice(0,40).map(function(a){return a[1]})}else{out=D.filter(function(x){return x.k==='Página'||x.k==='Guia'}).slice(0,12)}
res.innerHTML=out.length?out.map(function(x,i){return '<a href="'+x.u+'"'+(i===0?' class="sel"':'')+'><b>'+esc(x.t)+' <small>· '+esc(x.k)+'</small></b><small>'+esc((x.d||'').slice(0,110))+'</small></a>'}).join(''):'<a><small>Nada encontrado.</small></a>';sel=0}
q.oninput=function(){render(q.value)};
var f=$('#flt');if(f){f.oninput=function(){var v=f.value.toLowerCase();d.querySelectorAll('table.ref tbody tr').forEach(function(r){r.style.display=r.textContent.toLowerCase().indexOf(v)>-1?'':'none'})}}
})();
