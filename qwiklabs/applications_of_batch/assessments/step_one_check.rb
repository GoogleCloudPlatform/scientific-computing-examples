def step_one_check(handles:, maximum_score:, resources:)
  storage_handle = handles['primary_project.StorageV1']
  raise 'Invalid handle' if storage_handle.nil?
  # Check for bucket, stubbed for testing
  found_bucket = true
  unless found_bucket
    return { score: 0, message: 'bucket is missing' ,student_message: 'bucket_missing' }
  end
  # Check bucket configuration, stubbed for testing
  bucket_configured_correctly = true
  unless bucket_configured_correctly
    return { score: 2, message: 'bucket is misconfigured', student_message: 'bucket_misconfigured' }
  end
  { score: max_score, message: 'step completed', student_message: 'success' }
end
