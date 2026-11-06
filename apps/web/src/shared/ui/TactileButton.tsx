import type { ButtonHTMLAttributes } from 'react';

export function TactileButton({className='',children,...props}:ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={`tactile ${className}`} {...props}>{children}</button>;
}
