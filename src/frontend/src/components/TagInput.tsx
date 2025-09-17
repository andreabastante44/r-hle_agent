import React, { useState, KeyboardEvent } from 'react';

interface TagInputProps {
  label: string;
  tags: string[];
  onAdd: (tag: string) => void;
  onRemove: (tag: string) => void;
  placeholder?: string;
}

export const TagInput: React.FC<TagInputProps> = ({ label, tags, onAdd, onRemove, placeholder }) => {
  const [value, setValue] = useState('');

  const add = () => {
    const v = value.trim();
    if (!v) return;
    onAdd(v);
    setValue('');
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); add(); }
  };

  return (
    <div>
      <label className="text-xs font-medium text-slate-500 mb-1 block">{label}</label>
      <div className="flex flex-wrap gap-2 mb-2">
        {tags.map(t => (
          <span key={t} className="inline-flex items-center gap-1 bg-blue-100 text-blue-700 text-xs px-2 py-1 rounded">
            {t}
            <button onClick={() => onRemove(t)} className="text-blue-600 hover:text-blue-800">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={onKey}
          placeholder={placeholder || 'Enter & press Enter'}
          className="flex-1 h-9 rounded border px-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <button type="button" onClick={add} className="h-9 px-3 rounded bg-blue-600 hover:bg-blue-500 text-white text-sm">Add</button>
      </div>
    </div>
  );
};

export default TagInput;
