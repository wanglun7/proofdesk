import { useState, useCallback } from 'react'
import { AlertTriangle, Info } from 'lucide-react'

interface ModalState {
  type: 'alert' | 'confirm'
  title: string
  message: string
  resolve: (value: boolean) => void
}

export function useModalState() {
  const [modal, setModal] = useState<ModalState | null>(null)

  const showAlert = useCallback((title: string, message: string): Promise<void> => {
    return new Promise((resolve) => {
      setModal({ type: 'alert', title, message, resolve: () => { setModal(null); resolve() } })
    })
  }, [])

  const showConfirm = useCallback((title: string, message: string): Promise<boolean> => {
    return new Promise((resolve) => {
      setModal({
        type: 'confirm',
        title,
        message,
        resolve: (value: boolean) => { setModal(null); resolve(value) },
      })
    })
  }, [])

  return { modal, showAlert, showConfirm }
}

interface ModalProps {
  modal: ModalState | null
}

export default function Modal({ modal }: ModalProps) {
  if (!modal) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      onClick={() => modal.type === 'alert' && modal.resolve(true)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-2xl p-6 min-w-[320px] max-w-md mx-4"
      >
        <div className="flex items-start gap-3 mb-4">
          <div className={`flex items-center justify-center w-9 h-9 rounded-full shrink-0 ${
            modal.type === 'confirm' ? 'bg-red-100' : 'bg-blue-100'
          }`}>
            {modal.type === 'confirm'
              ? <AlertTriangle size={16} className="text-red-600" />
              : <Info size={16} className="text-blue-600" />
            }
          </div>
          <div>
            <div className="font-semibold text-[15px] text-slate-900 leading-tight">
              {modal.title}
            </div>
            <div className="text-[13px] text-slate-500 mt-1 leading-relaxed">
              {modal.message}
            </div>
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          {modal.type === 'confirm' && (
            <button
              onClick={() => modal.resolve(false)}
              className="px-4 py-2 text-sm border border-slate-200 rounded-md bg-white text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
          )}
          <button
            onClick={() => modal.resolve(true)}
            className={`px-4 py-2 text-sm rounded-md text-white font-semibold transition-colors ${
              modal.type === 'confirm'
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-brand-600 hover:bg-brand-700'
            }`}
          >
            {modal.type === 'confirm' ? 'Delete' : 'OK'}
          </button>
        </div>
      </div>
    </div>
  )
}
