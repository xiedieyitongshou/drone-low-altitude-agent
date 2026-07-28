import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getMyProfile, updateMyProfile } from '../api/profile'
import type { UserProfile, UserProfileUpdateRequest } from '../types/profile'

type ProfileForm = {
  default_location: string
  default_task_type: string
  default_start_time: string
  default_end_time: string
  output_style: string
  common_locations: string
  common_task_types: string
}

const emptyForm: ProfileForm = {
  default_location: '',
  default_task_type: 'cruise',
  default_start_time: '',
  default_end_time: '',
  output_style: 'concise',
  common_locations: '',
  common_task_types: 'cruise',
}

function toForm(profile: UserProfile): ProfileForm {
  return {
    default_location: profile.default_location ?? '',
    default_task_type: profile.default_task_type ?? 'cruise',
    default_start_time: profile.default_start_time ?? '',
    default_end_time: profile.default_end_time ?? '',
    output_style: profile.output_style ?? 'concise',
    common_locations: profile.common_locations.join('，'),
    common_task_types: profile.common_task_types.join('，'),
  }
}

function splitList(value: string) {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [form, setForm] = useState<ProfileForm>(emptyForm)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  useEffect(() => {
    async function loadProfile() {
      setIsLoading(true)
      setErrorMessage('')

      try {
        const response = await getMyProfile()
        setProfile(response)
        setForm(toForm(response))
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : '加载 Profile 失败')
      } finally {
        setIsLoading(false)
      }
    }

    void loadProfile()
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setErrorMessage('')
    setSuccessMessage('')

    const payload: UserProfileUpdateRequest = {
      default_location: form.default_location.trim() || null,
      default_task_type: form.default_task_type.trim() || null,
      default_start_time: form.default_start_time.trim() || null,
      default_end_time: form.default_end_time.trim() || null,
      output_style: form.output_style.trim() || null,
      common_locations: splitList(form.common_locations),
      common_task_types: splitList(form.common_task_types),
    }

    try {
      const response = await updateMyProfile(payload)
      setProfile(response)
      setForm(toForm(response))
      setSuccessMessage('Profile 已保存。')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '保存 Profile 失败')
    } finally {
      setIsSaving(false)
    }
  }

  function updateField<Key extends keyof ProfileForm>(field: Key, value: ProfileForm[Key]) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  return (
    <section className="page-card profile-page">
      <div className="page-header">
        <div>
          <h2>用户 Profile 设置</h2>
          <p>
            该页面调用 <code>/users/me/profile</code>
            ，用于维护当前用户长期偏好。自然语言缺少地点、任务类型或时间段时，Agent
            可以从这里补全。
          </p>
        </div>
      </div>

      {isLoading ? <div className="loading-panel">正在加载 Profile...</div> : null}
      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}
      {successMessage ? <div className="success-panel">{successMessage}</div> : null}

      {!isLoading ? (
        <form className="agent-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              <span>默认地点</span>
              <input
                value={form.default_location}
                onChange={(event) => updateField('default_location', event.target.value)}
                placeholder="例如：深圳湾"
              />
            </label>

            <label>
              <span>默认任务类型</span>
              <select
                value={form.default_task_type}
                onChange={(event) => updateField('default_task_type', event.target.value)}
              >
                <option value="cruise">日常巡航</option>
                <option value="inspection">巡检任务</option>
                <option value="hover">悬停拍摄</option>
                <option value="survey">测绘任务</option>
              </select>
            </label>

            <label>
              <span>默认开始时间</span>
              <input
                type="time"
                value={form.default_start_time}
                onChange={(event) => updateField('default_start_time', event.target.value)}
              />
            </label>

            <label>
              <span>默认结束时间</span>
              <input
                type="time"
                value={form.default_end_time}
                onChange={(event) => updateField('default_end_time', event.target.value)}
              />
            </label>

            <label>
              <span>输出风格</span>
              <select
                value={form.output_style}
                onChange={(event) => updateField('output_style', event.target.value)}
              >
                <option value="concise">简洁</option>
                <option value="detailed">详细</option>
              </select>
            </label>
          </div>

          <label>
            <span>常用地点</span>
            <textarea
              value={form.common_locations}
              onChange={(event) => updateField('common_locations', event.target.value)}
              rows={3}
              placeholder="用逗号分隔，例如：深圳湾，南山区，宝安机场附近"
            />
          </label>

          <label>
            <span>常用任务类型</span>
            <textarea
              value={form.common_task_types}
              onChange={(event) => updateField('common_task_types', event.target.value)}
              rows={2}
              placeholder="用逗号分隔，例如：cruise，inspection，survey"
            />
          </label>

          <div className="form-actions">
            <button type="submit" disabled={isSaving}>
              {isSaving ? '保存中...' : '保存 Profile'}
            </button>
          </div>
        </form>
      ) : null}

      {profile ? (
        <div className="profile-summary">
          <div>
            <span>user_id</span>
            <strong>{profile.user_id}</strong>
          </div>
          <div>
            <span>最近更新</span>
            <strong>{profile.updated_at}</strong>
          </div>
        </div>
      ) : null}
    </section>
  )
}
