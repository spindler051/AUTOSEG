// Abre a conversa após confirmação de OS salva. O WhatsApp exige envio manual.
(function(){
  const el=document.getElementById('whatsapp-automatico');
  if(!el)return;
  const url=el.getAttribute('data-url');
  if(!url || !/^https:\/\/wa\.me\/\d+\?text=/.test(url))return;
  const key='autosseg-wa-'+el.getAttribute('data-id');
  try{if(sessionStorage.getItem(key))return;sessionStorage.setItem(key,'1');}catch(e){}
  // Navegação na mesma aba evita bloqueio de janelas emergentes.
  // A OS permanece gravada mesmo que o WhatsApp não seja enviado.
  window.location.assign(url);
})();
