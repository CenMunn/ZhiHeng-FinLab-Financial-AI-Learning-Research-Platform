import { useEffect, useRef, type ReactNode } from 'react';

export function ModalFrame({titleId,onClose,className='',children}:{titleId:string;onClose:()=>void;className?:string;children:ReactNode}) {
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    const trigger=document.activeElement as HTMLElement|null;
    const element=dialog.current!;
    element.showModal();
    return()=>{element.close();if(trigger?.isConnected)trigger.focus();};
  },[]);
  return <dialog ref={dialog} className={`workspace-dialog ${className}`} aria-labelledby={titleId}
    onCancel={event=>{event.preventDefault();onClose();}}
    onClick={event=>{if(event.target===event.currentTarget)onClose();}}>
    <div className="dialog-content">{children}</div>
  </dialog>;
}
